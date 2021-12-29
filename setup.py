import os
from setuptools import setup

base_dir = os.path.dirname(os.path.realpath(__file__))

setup(
    name='argus',
    version='0.5.1',
    packages=["argus.db", "argus.backend"],
    include_package_data=True,
    zip_safe=False,
    install_requires=open(os.path.join(base_dir,'requirements.txt')).readlines(),
    test_requires=open(os.path.join(base_dir,'requirements_test.txt')).readlines(),

)
