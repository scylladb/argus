import time
from typing import Optional
from threading import Thread, Event
from werkzeug.serving import is_running_from_reloader
from flask import Flask
from argus.backend.db import ScyllaCluster
from argus.backend.models import WebCategoryGroup, WebRelease, WebNemesis


class PollingDataCollector():
    INSTANCE: Optional['PollingDataCollector'] = None

    def __init__(self, *args, **kwargs):
        self.cluster = ScyllaCluster.get()
        self.poll_period = 60
        self._shutdown_event = Event()
        self._thread = Thread(name="PollingNewTestRunData", target=self.data_collector, daemon=True)

    @classmethod
    def get(cls):
        if is_running_from_reloader():
            return
        if cls.INSTANCE:
            return cls.INSTANCE
        cls.INSTANCE = PollingDataCollector()
        cls.INSTANCE.start()

        return cls.INSTANCE

    @classmethod
    def destroy(cls):
        if not cls.INSTANCE:
            return
        cls.INSTANCE.shutdown()
        cls.INSTANCE = None

    def start(self):
        self._thread.start()

    def shutdown(self):
        self._shutdown_event.set()

    def data_collector(self):
        while not self._shutdown_event.is_set():
            session = self.cluster.create_session()
            existing_releases = [release.name for release in WebRelease.all()]
            existing_nemeses = [nemesis.name for nemesis in WebNemesis.all()]
            existing_groups = [group.name for group in WebCategoryGroup.all()]

            run_data = session.execute(
                "SELECT release_name, group, nemesis_data FROM test_runs").all()

            new_releases = set(
                map(lambda v: v["release_name"], run_data)) - set(existing_releases)
            new_groups = set(
                map(lambda v: v["group"], run_data)) - set(existing_groups)
            new_nemeses = map(lambda v: v["nemesis_data"], run_data)
            new_nemeses = set(
                [nemesis.name for nemesis_data in new_nemeses if nemesis_data for nemesis in nemesis_data]
            ) - set(existing_nemeses)

            for nemesis in new_nemeses:
                web_nemesis = WebNemesis()
                web_nemesis.name = nemesis
                web_nemesis.save()
                existing_nemeses.append(nemesis)

            for group in new_groups:
                web_release = WebCategoryGroup()
                web_release.name = group
                web_release.save()
                existing_groups.append(group)

            for release in new_releases:
                web_group = WebRelease()
                web_group.name = release
                web_group.save()
                existing_releases.append(release)

            self.cluster.shutdown_session(session=session)
            time.sleep(self.poll_period)
