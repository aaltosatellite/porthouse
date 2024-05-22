import sys
import setuptools
from setuptools.command.install import install

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)
        #
        # Auto-create the configuration files
        #
        from porthouse.core.config import create_template_config
        create_template_config()


setuptools.setup(
    name="porthouse",
    version="0.1.1",
    author="Aalto Satellites",
    author_email="petri.niemela@aalto.fi, olli.knuuttila@gmail.com",
    description="Groundstation and mission control software",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aaltosatellite/porthouse",
    packages=[ f"porthouse.{name}" for name in setuptools.find_packages() ],
    package_dir={ 'porthouse': '.' },
    python_requires='>=3.8',
    install_requires=[ # Minimal requirements
        "aiormq",
        "amqp",
        "httpx",
        "numpy",
        "quaternion",
        "pandas",
        "prompt_toolkit",
        "ptpython",
        "pyserial",
        "pyYAML",
        "pyzmq",
        "requests",
        "skyfield",
        "sortedcontainers",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPLv3 License",
        "Operating System :: OS Independent",
    ],
    scripts=[
        "bin/porthouse"
    ],
    cmdclass={
        'install': PostInstallCommand,
    }
)

if "develop" in sys.argv and "--user" in sys.argv:
    #
    # THE NORMAL INSTALLATION IN THE DEVELOPE MODE DOESN'T WORK
    # THANKS TO THIS LONGLASTING ISSUE: https://github.com/pypa/setuptools/issues/230
    #
    # This workaround removes the .egg-link file created by the setuptools
    # and creates a symbolic link from site-packages to this folder.
    #
    import os, site

    # Remove broken egg-link
    egg_file = os.path.join(site.USER_SITE, "porthouse.egg-link")
    print(f"Removing broken egg-file: {egg_file!r}")
    os.unlink(egg_file)

    # Create symbolic link
    src = os.path.join(site.USER_SITE, "porthouse")
    dst = os.path.dirname(os.path.realpath(__file__))
    try:
        os.unlink(src)
        print(f"Removed the old symlink {src!r}")
    except FileNotFoundError:
        pass
    print(f"Making symbolic link: {src!r} -> {dst!r}")
    os.symlink(dst, src)
