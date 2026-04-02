# Third-Party Notices

This project depends on third-party software with separate licenses.

## ORB-SLAM3

- Project: ORB-SLAM3
- Upstream: [https://github.com/UZ-SLAMLab/ORB_SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3)
- License: GNU General Public License v3.0 (GPL-3.0), per upstream repository
- Notes: If you distribute binaries or source that include ORB-SLAM3 or derivative works,
  you must comply with GPL-3.0 obligations.

## orbslam3-python (Python binding)

- Package: orbslam3-python (v2.0.0 on PyPI)
- Upstream: [https://github.com/AlexandruRO45/ORB_SLAM-PythonBindings](https://github.com/AlexandruRO45/ORB_SLAM-PythonBindings)
- License: BSD 2-Clause License, per upstream repository and PyPI metadata
- Notes: This project uses the binding as an external dependency and does not re-license it.
  The binding itself wraps ORB-SLAM3 (GPL-3.0); redistributors bundling the compiled binding
  should verify GPL-3.0 obligations for the linked ORB-SLAM3 code.

## Intel RealSense SDK / pyrealsense2

- Project: librealsense / pyrealsense2
- Upstream: [https://github.com/IntelRealSense/librealsense](https://github.com/IntelRealSense/librealsense)
- License: Apache License 2.0, per upstream repository

## OpenCV (opencv-python)

- Project: OpenCV / opencv-python
- Upstream: [https://github.com/opencv/opencv](https://github.com/opencv/opencv)
- License: Apache License 2.0 (OpenCV core), plus package-specific notices

## NumPy

- Project: NumPy
- Upstream: [https://github.com/numpy/numpy](https://github.com/numpy/numpy)
- License: BSD-3-Clause

## Matplotlib

- Project: Matplotlib
- Upstream: [https://github.com/matplotlib/matplotlib](https://github.com/matplotlib/matplotlib)
- License: Matplotlib License (BSD-style)

## pyserial

- Project: pyserial
- Upstream: [https://github.com/pyserial/pyserial](https://github.com/pyserial/pyserial)
- License: BSD-3-Clause

## Responsibility

End users and redistributors are responsible for ensuring full compliance with
all applicable third-party licenses when shipping source, binaries, containers,
or integrated products.
