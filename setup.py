from setuptools import setup, find_packages


setup(
    name='argus.py',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pytest',
        'scylla-driver',
        'pyyaml'
    ],
)
