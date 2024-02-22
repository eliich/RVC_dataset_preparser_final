from setuptools import setup, find_packages

setup(
    name='RVC_dataset_preparser',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'moviepy',
        'pygame',
        'pyinstaller',
    ],
)
