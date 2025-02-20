from setuptools import setup, find_packages

setup(
    name="audio_transcriber",
    version="0.4.1",
    package_dir={"": "src"},
    packages=find_packages(where="src", include=["audio_transcriber", "audio_transcriber.*"]),
    install_requires=[
        'pyaudiowpatch>=0.2.12',
        'audioop-lts>=0.2.1',
        'numpy>=1.24.3',
        'aiofiles>=23.2.1',
        'psutil>=5.9.5',
        'pywin32>=306',
        'comtypes>=1.2.0',
        'python-json-logger>=2.0.7',
        'pytest>=7.4.0',
    ],
    python_requires='>=3.13',
)
