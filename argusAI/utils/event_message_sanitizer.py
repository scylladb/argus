import os
import re
from datetime import datetime

from typing import Pattern, List, Callable
from uuid import UUID


class MessageSanitizer:
    """
    A class used to sanitize event messages by removing or replacing sensitive information
    such as IP addresses, URLs, file paths, and other identifiable data.

    Sanitized messages are written to a file for further analysis.
    """

    def __init__(self):
        self.event_pattern: Pattern = re.compile(r"Severity\.(ERROR|CRITICAL|WARNING|INFO)\)")
        self.event_id_pattern: Pattern = re.compile(
            r"(?:event_id=)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        )
        self.ip_pattern = re.compile(
            r"\b(?:"
            r"(?:\d{1,3}\.){3}\d{1,3}"  # IPv4
            r"|"
            r"(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4})"  # Full IPv6
            r"|"
            r"[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){0,6}::[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{1,4}){0,6}"  # IPv6 with ::
            r")\b",
            re.IGNORECASE,
        )
        self.scylla_data_path = re.compile(r"[^\s\[\(:]*/scylla/data/[^\s\]\)]*")
        self.sct_path = re.compile(r"[^\s\[\(:]*/scylla-cluster-tests/[^\s\]\)]*")
        self.filepath_pattern = re.compile(
            r"(?:/|\b)[\w/.-]*(?:libreloc/)?[\w.-]+\.(so|py|cpp|sh|db|txt)(?:\+0x[0-9a-fA-F]+)?\b"
        )
        self.field_patterns: List[Pattern] = [
            re.compile(r"period_type=\S+"),
            re.compile(r"(target_)?node=Node\s+[\w\-\.]+\s*\[.*?\]"),
            re.compile(r"node=[\w\-\.]+\s*\[.*?\]"),
            re.compile(r"executable=/[\w/]+\s+executable_version=[\d\.]"),
            re.compile(r"line_number[=:\s]*[\d]+"),
        ]
        self.traceback_pattern: Pattern = re.compile(r'File "[^"]+", line \d+, in ([\w_]+)\s*')
        self.url_pattern: Pattern = re.compile(
            r"(corefile_url=|download_instructions:)\s*https?://[^\s]+|gsutil cp gs://[^\s]+"
        )
        self.metadata_pattern: Pattern = re.compile(
            r"(PID|UID|GID|Timestamp|Command Line|Executable|Control Group|Unit|Slice|Boot ID|"
            r"Machine ID|Hostname|Storage|Size on Disk|Message|Disk Size):.*?(?=\n|$)",
            re.MULTILINE,
        )
        self.report_at_pattern: Pattern = re.compile(r"Please report: at .*\n")
        self.lib_address_pattern: Pattern = re.compile(r"\([^()]+ \+ 0x[0-9a-fA-F]+\)")
        self.module_pattern: Pattern = re.compile(r"Module [^\n]+ from rpm [^\n]+")
        self.stack_header_pattern: Pattern = re.compile(r"Stack trace of thread \d+:")
        self.stack_line_pattern: Pattern = re.compile(r"#\d+\s+0x[0-9a-fA-F]+\s+([^\s(]+)")
        self.quote_pattern: Pattern = re.compile(r'[\'"]')
        self.memory_address_pattern = re.compile(r"0x[0-9a-fA-F]+")
        self.node_name_pattern = re.compile(r"(node\s+|Node\s+)?[\w-]+\-(db|loader|monitor)-node-[\w-]+\d+")
        self.process_id_pattern = re.compile(r"\[scylla\[\d+\]\]:?")
        self.iso_timestamp_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}_\d{3}\+\d{2}:\d{2}")
        self.special_chars = re.compile(r"[|[\]:,]")
        self.eol_pattern = re.compile(r"\\n")
        self.backslashes_pattern = re.compile(r"\\")
        self.repetitions_pattern = re.compile(r"(\b\w+\b)(?:\s+\1)+")
        self.backtrace_unwanted_lines = {
            "seastar::backtrace",
            "seastar::print_with_backtrace",
            "seastar::install_oneshot_signal_handler",
            "seastar::current_backtrace",
            "seastar::current_tasktrace",
            "seastar::memory::cpu_pages::warn_large_allocation",
            "seastar::memory::allocate_slowpath",
            "at main.cc:",
            " ??:",
        }

        self.sanitizers: List[Callable[[str], str]] = [
            self.remove_preface,
            self.remove_iso_timestamps,
            self.remove_severity_levels,
            self.remove_specific_fields,
            self.remove_event_ids,
            self.remove_ip_addresses,
            self.remove_urls,
            self.remove_metadata,
            self.remove_backtrace_unwanted_lines,
            self.remove_modules,
            self.remove_message_prefix,
            self.remove_report_at,
            self.remove_lib_address,
            self.remove_process_ids,
            self.remove_memory_addresses,
            self.truncate_traceback,
            self.simplify_stack_trace,
            self.remove_redundant_punctuation,
            self.remove_quotes,
            self.remove_eol,
            self.remove_backslashes,
            self.truncate_long_words,
            self.remove_node_names,
            self.remove_scylla_data_paths,
            self.remove_sct_paths,
            self.remove_repetitions,
            self.simplify_namespaces,
            self.remove_iso_timestamps,
            self.remove_special_chars,
            self.normalize_whitespace,
        ]
        os.makedirs("logs", exist_ok=True)
        self.sanitized_messages_fp = open(
            "logs/sanitized_messages_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log", "w"
        )

    def sanitize(self, run_id: UUID, message: str) -> str:
        result = message
        for sanitizer in self.sanitizers:
            result = sanitizer(result)
        self.sanitized_messages_fp.write(f"{run_id}: {result}\n")
        return result

    def remove_preface(self, text: str) -> str:
        try:
            date = text.split(" ", 1)[0]
        except IndexError:
            return text
        try:
            return date + " " + text.split("(", 1)[1]
        except IndexError:
            return text

    def remove_scylla_data_paths(self, text: str) -> str:
        return self.scylla_data_path.sub("DATA", text)

    def remove_sct_paths(self, text: str) -> str:
        return self.sct_path.sub("SCT", text)

    def remove_lib_address(self, text: str) -> str:
        return self.lib_address_pattern.sub("", text)

    def truncate_long_words(self, text: str) -> str:
        """Long words are not fitting well and cause very long processing. truncate it."""
        return " ".join([word[:100] for word in text.split()])

    def remove_severity_levels(self, text: str) -> str:
        return self.event_pattern.sub("", text)

    def remove_event_ids(self, text: str) -> str:
        return self.event_id_pattern.sub("ID", text)

    def remove_ip_addresses(self, text: str) -> str:
        return self.ip_pattern.sub("IP", text)

    def remove_urls(self, text: str) -> str:
        return self.url_pattern.sub("URL", text)

    def remove_metadata(self, text: str) -> str:
        return self.metadata_pattern.sub("", text)

    def remove_modules(self, text: str) -> str:
        return self.module_pattern.sub("", text)

    def remove_file_paths(self, text: str) -> str:
        return self.filepath_pattern.sub("FP", text)

    def remove_specific_fields(self, text: str) -> str:
        result = text
        for pattern in self.field_patterns:
            result = pattern.sub("", result)
        return result

    def remove_message_prefix(self, text: str) -> str:
        return re.sub(r"message[ =]", "", text)

    def truncate_traceback(self, text: str) -> str:
        text = self.traceback_pattern.sub(r"in \1 ", text)
        text = re.sub(r"Traceback \(most recent call last\):", "TB ", text)
        return text

    def simplify_stack_trace(self, text: str) -> str:
        text = re.sub(r"(0x[0-9a-fA-F]+\s*)+(?!\w)", "", text)
        text = self.stack_header_pattern.sub("Stack:", text)
        stack_lines = self.stack_line_pattern.findall(text)
        if stack_lines:
            text = re.sub(
                r"Stack trace of thread \d+:.*?(?=\nStack trace|$)",
                f"Stack: {' '.join(stack_lines)}",
                text,
                flags=re.DOTALL,
            )
        return text

    def remove_redundant_punctuation(self, text: str) -> str:
        text = re.sub(r"\(([\w]+)\)", r"\1", text)
        text = re.sub(r"\(([\w\.]+\) *\(\))", r"\1", text)
        text = re.sub(r"[=]", " ", text)
        return text

    def remove_quotes(self, text: str) -> str:
        return self.quote_pattern.sub("", text)

    def simplify_namespaces(self, text: str) -> str:
        return re.sub(r"(\w+)\.(\w+)", r"\1_\2", text)

    def normalize_whitespace(self, text: str) -> str:
        return " ".join(text.split())

    def remove_memory_addresses(self, text: str) -> str:
        return self.memory_address_pattern.sub("", text)

    def remove_node_names(self, text: str) -> str:
        return self.node_name_pattern.sub(r"\2", text)

    def remove_process_ids(self, text: str) -> str:
        return self.process_id_pattern.sub("", text)

    def remove_iso_timestamps(self, text: str) -> str:
        return self.iso_timestamp_pattern.sub("", text)

    def remove_special_chars(self, text: str) -> str:
        return self.special_chars.sub(" ", text)

    def remove_backslashes(self, text: str) -> str:
        return self.backslashes_pattern.sub("", text)

    def remove_eol(self, text: str) -> str:
        return self.eol_pattern.sub(" ", text)

    def remove_repetitions(self, text: str) -> str:
        return self.repetitions_pattern.sub(r"\1", text)

    def remove_report_at(self, text: str) -> str:
        return self.report_at_pattern.sub("", text)

    def _remove_inlined_starting(self, text: str) -> str:
        """Remove inlined starting text that is not useful."""
        if not text.startswith("(inlined by) "):
            return text
        return text.split("(inlined by) ", 1)[-1].strip()

    def remove_backtrace_unwanted_lines(self, text: str) -> str:
        """Specific lines in backtrace that are not useful and can be removed."""
        if not "backtrace" in text[:1000]:
            return text
        return "\n".join(
            self._remove_inlined_starting(line)
            for line in text.splitlines()
            if not any(problem in line for problem in self.backtrace_unwanted_lines)
        )
