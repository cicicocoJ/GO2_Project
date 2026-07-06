from setuptools import setup

package_name = 'go2_camera_capture'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='unitree',
    maintainer_email='unitree@example.com',
    description='D435i RGB camera capture node for GO2 inspection system.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'camera_capture_node = go2_camera_capture.camera_capture_node:main',
        ],
    },
)
