from setuptools import setup, find_packages


setup(
    name='argus',
    version='0.3.2',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pydantic==1.8.2',
        'scylla-driver==3.24.7',
        'pyyaml==5.4.1'
    ],
)
