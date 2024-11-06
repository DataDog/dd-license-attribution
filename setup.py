from setuptools import setup, find_packages

setup(
    name="ospo-tools",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "agithub",
        "scancode-toolkit",
        "typer",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "pytest-mock",
            "mypy",
            "black",
        ],
    },
    entry_points={
        "console_scripts": [
            "generate_3rd_party_csv=ospo_tools.generate_3rd_party_csv:cli",
        ],
    },
    author="Damian Vicino",
    author_email="damian.vicino@datadoghq.com",
    description="A set of tools to help with the OSPO activities and reporting",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/DataDog/ospo-tools",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
