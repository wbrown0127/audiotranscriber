# 🎙️ Audio Transcriber

> ⚠️ **Experimental Project Alert!** This is a work in progress and highly experimental. Expect bugs, crashes, and general chaos. You've been warned! 🚧

## 🎯 What is this?

A Python-based real-time audio transcription system using Whisper AI, built as my first project with AI assistance! It's designed to capture audio from Windows systems (using WASAPI) and turn it into text, with some ambitious goals around performance and stability.

## ✨ Features (or... attempts at features 😅)

- 🎤 Real-time audio capture through WASAPI
- 🧠 Whisper AI integration for transcription
- 👥 Speaker isolation and channel separation
- ⚡ Trying really hard to be fast (targeting <50ms latency)
- 📊 Probably over-engineered monitoring system
- 🎛️ Work-in-progress GUI (it's... getting there!)

## 🚀 Current Status

This project is in active development and extremely unstable. Here's what's cooking:

- 🏗️ Core Architecture: Mostly working... sometimes
- 🔧 Stability: We're trying our best!
- 🎯 GUI: About 60% complete (native features pending)
- 📦 Deployment: 40% complete (MSIX packaging coming... eventually)

## 🛠️ System Requirements

### Minimum (it might run... no promises)
- CPU: i5-8250U (AVX2 support required)
- RAM: 4GB DDR4 (2GB for our hungry buffer system)
- Storage: 100MB SATA
- OS: Windows 10 22H2 or later
- Python: 3.13 or later

### Recommended (still might not help 😉)
- CPU: i7-4790K
- RAM: 8GB DDR4
- Storage: 100MB NVMe
- Audio: VB-Cable + Hardware interface

## 🏗️ Architecture

This project might be over-engineered, but hey, we're having fun! Here's what we're working with:

### Core Components
- 🎤 Audio Capture (WASAPI integration)
- 📊 Signal Processing
- 🗣️ Transcription (Whisper integration)
- 📈 Monitoring System

### Support Components
- 🎮 Component Coordinator
- 🏊 ResourcePool (fancy tiered buffer system)
- 📦 Buffer Manager
- ⚠️ Alert System (it will tell you when things go wrong... which is often)

## 🧪 Testing

We've got tests! Lots of them! Are they all passing? Well... 

- Total Tests: 130
- Passing: Let's just say we're working on it 😅
- Coverage Target: 100% (we dream big!)

## 🚀 Getting Started

1. Clone this repository (if you dare)
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Cross your fingers
4. Run the application:
```bash
python src/audio_transcriber/main.py
```
5. Hope for the best! 🤞

## 🤝 Contributing

Found a bug? That's not surprising! Want to help? We'd love that! Here's how:

1. Fork the repository
2. Create your feature branch
3. Make your changes
4. Run the tests (or add new ones!)
5. Submit a pull request

## 📝 License

This project is licensed under the terms included in the LICENSE file. Use at your own risk! 😉

## 🙏 Acknowledgments

- OpenAI's Whisper for making this possible
- My AI assistant for helping create this chaos
- You, for being brave enough to check out this project!

---

*Remember: This is an experimental project. If it works, great! If it doesn't... well, that's part of the adventure! 🎢*
