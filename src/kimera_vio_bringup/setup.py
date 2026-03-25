import os
from glob import glob
from setuptools import setup

package_name = "kimera_vio_bringup"

setup(
    name=package_name,
    version="1.0.0",
    packages=[],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "launch"),
            glob(os.path.join("launch", "*launch.[pxy][yma]*")),
        ),
        (
            os.path.join("share", package_name, "config"),
            glob(os.path.join("config", "*.yaml")),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="linkerbot",
    maintainer_email="helloworld@linkerbot.cn",
    description="ROS2 bringup package for RealSense D455 and Kimera-VIO integration.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={},
)
