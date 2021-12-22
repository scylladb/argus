from setuptools import setup

setup(
    name='argus',
    version='0.5.0',
    packages=["argus.db", "argus.backend"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pydantic==1.8.2',
        'scylla-driver==3.24.7',
        'pyyaml==5.4.1'
    ],
    test_requires=[
        "coverage==5.5",
        "docker==4.4.4",
        "pytest==6.2.5",
    ]
)
