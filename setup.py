import setuptools


setuptools.setup(
    name='fmakefile',
    version='0.2.0a',
    author='Anton Zakharov',
    author_email='abzakharov@karazin.ua',
    description='Fortran makefile generator',
    long_description='Fortran makefile generator',
    long_description_content_type="text/markdown",
    url='none',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
