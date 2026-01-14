"""
Setup script for Pump.fun X/Twitter AI Agent.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="pumpfun-twitter-agent",
    version="1.0.0",
    author="ClaudeXAgent Team",
    description="An autonomous AI agent for generating and posting Pump.fun content to X/Twitter",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/ClaudeXAgent",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "pumpfun-agent=src.main:main",
        ],
    },
)
