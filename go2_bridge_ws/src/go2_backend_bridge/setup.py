from setuptools import setup

package_name = 'go2_backend_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        # Register this package in the ament index.
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name]
        ),
        # Install package.xml so ROS2 tools can inspect package metadata.
        (
            'share/' + package_name,
            ['package.xml']
        ),
    ],
    install_requires=[
        'setuptools',
        # websockets is used by backend_client_node.py to connect to the backend.
        'websockets',
    ],
    zip_safe=True,
    maintainer='unitree',
    maintainer_email='unitree@example.com',
    description='Minimal ROS2 backend bridge for Unitree GO2 EDU Jetson.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # This enables:
            # ros2 run go2_backend_bridge backend_client_node
            'backend_client_node = go2_backend_bridge.backend_client_node:main',
        ],
    },
)
