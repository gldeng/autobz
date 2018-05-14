from setuptools import setup, find_packages
import os

this_dir = os.path.dirname(__file__)
install_requires = [
    x.strip() for x in open(os.path.join(this_dir, 'requirements.txt'))
    if x.strip()
]

setup(
    name="autobz" ,
    version="0.1.1" ,
    description="autobz",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'autobz = autobz:main',
        ],
    },
)
