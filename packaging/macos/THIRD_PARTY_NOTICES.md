# Third-party software in Transcribe.app

Transcribe itself is licensed under the MIT License (see `LICENSE`). The macOS app bundles the following third-party software. The full license texts are in the `licenses` folder inside the app (`Transcribe.app/Contents/Resources/licenses`).

| Component | License | Source |
|-----------|---------|--------|
| Python | PSF License | https://www.python.org |
| FFmpeg 8.1.3 (`ffmpeg`, `ffprobe`; audio decoders only, no GPL or non-free parts) | LGPL 2.1 or later | https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz, also attached to every release of Transcribe; build flags in `packaging/macos/build_ffmpeg.sh` |
| MLX | MIT | https://github.com/ml-explore/mlx |
| mlx-whisper | MIT | https://github.com/ml-explore/mlx-examples |
| NumPy | BSD 3-Clause | https://numpy.org |
| SciPy | BSD 3-Clause | https://scipy.org |
| Numba | BSD 2-Clause | https://numba.pydata.org |
| llvmlite (includes LLVM) | BSD 2-Clause; LLVM: Apache 2.0 with LLVM Exception | https://github.com/numba/llvmlite |
| tiktoken | MIT | https://github.com/openai/tiktoken |
| huggingface_hub | Apache 2.0 | https://github.com/huggingface/huggingface_hub |
| tqdm | MIT / MPL 2.0 | https://github.com/tqdm/tqdm |
| pywebview | BSD 3-Clause | https://github.com/r0x0r/pywebview |
| PyObjC | MIT | https://github.com/ronaldoussoren/pyobjc |
| PyInstaller bootloader | GPL 2.0 with bootloader exception | https://pyinstaller.org |

The Whisper models (downloaded on first use from Hugging Face, `mlx-community`) are released by OpenAI under the MIT License.
