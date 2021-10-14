from setuptools import setup, find_packages


setup(
    name='argus',
    version='0.2',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pytest',
        'pydantic',
        'docker',
        'coverage',
        'scylla-driver',
        'pyyaml'
    ],
)
