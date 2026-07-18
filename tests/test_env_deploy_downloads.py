import unittest

from src.env_deploy_panel import (
    CUDA_DOWNLOAD_ROOT,
    DownloadSource,
    _build_conda_download_urls,
    _build_cuda_download_urls,
    _parse_cuda_installer_links,
    _parse_cuda_versions_from_archive,
)


class EnvDeployDownloadTests(unittest.TestCase):
    def test_parse_cuda_versions_filters_12_9_and_newer(self):
        html = """
        <a href="/cuda-12-8-2-download-archive">CUDA 12.8.2</a>
        <a href="/cuda-12-9-0-download-archive">CUDA 12.9.0</a>
        <a href="/cuda-13-0-3-download-archive">CUDA 13.0.3</a>
        <a href="/cuda-13-2-1-download-archive">CUDA 13.2.1</a>
        """

        self.assertEqual(
            _parse_cuda_versions_from_archive(html),
            ["13.2.1", "13.0.3", "12.9.0"],
        )

    def test_parse_cuda_installer_links_for_target(self):
        html = """
        https://developer.download.nvidia.com/compute/cuda/12.9.0/local_installers/cuda_12.9.0_575.51.03_linux.run
        https://developer.download.nvidia.com/compute/cuda/12.9.0/local_installers/cuda_12.9.0_576.02_windows.exe
        https://developer.download.nvidia.com/compute/cuda/12.9.0/network_installers/cuda_12.9.0_windows_network.exe
        """

        self.assertEqual(
            _parse_cuda_installer_links(html, "12.9.0", "windows"),
            [
                "https://developer.download.nvidia.com/compute/cuda/12.9.0/local_installers/cuda_12.9.0_576.02_windows.exe",
            ],
        )
        self.assertEqual(
            _parse_cuda_installer_links(html, "12.9.0", "wsl"),
            [
                "https://developer.download.nvidia.com/compute/cuda/12.9.0/local_installers/cuda_12.9.0_575.51.03_linux.run",
            ],
        )

    def test_cuda_mirror_urls_fall_back_to_official(self):
        mirror = DownloadSource("deploy_source_ustc", "https://mirrors.example.test/nvidia-cuda")
        official = f"{CUDA_DOWNLOAD_ROOT}/12.9.0/local_installers/cuda_12.9.0_575.51.03_linux.run"

        self.assertEqual(
            _build_cuda_download_urls([official], mirror),
            [
                "https://mirrors.example.test/nvidia-cuda/12.9.0/local_installers/cuda_12.9.0_575.51.03_linux.run",
                official,
            ],
        )

    def test_conda_mirror_urls_fall_back_to_official(self):
        mirror = DownloadSource("deploy_source_tuna", "https://mirrors.example.test/anaconda")

        self.assertEqual(
            _build_conda_download_urls("Miniconda3", "windows", mirror),
            [
                "https://mirrors.example.test/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe",
                "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe",
            ],
        )


if __name__ == "__main__":
    unittest.main()
