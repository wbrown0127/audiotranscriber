import pyaudiowpatch as pyaudio

def check_wasapi_devices():
    print("Checking WASAPI Audio Devices...")
    p = pyaudio.PyAudio()
    
    try:
        # Get WASAPI host API info
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        if wasapi_info is None:
            print("WASAPI API not found!")
            return
            
        print(f"\nWASAPI Info:")
        print(f"Default Input Device: {wasapi_info.get('defaultInputDevice', 'None')}")
        print(f"Default Output Device: {wasapi_info.get('defaultOutputDevice', 'None')}")
        
        # List all devices
        print("\nAll Audio Devices:")
        for i in range(p.get_device_count()):
            try:
                dev_info = p.get_device_info_by_index(i)
                
                # Only show WASAPI devices
                if dev_info['hostApi'] == wasapi_info['index']:
                    print(f"\nDevice {i}:")
                    print(f"Name: {dev_info['name']}")
                    print(f"Max Input Channels: {dev_info['maxInputChannels']}")
                    print(f"Max Output Channels: {dev_info['maxOutputChannels']}")
                    print(f"Default Sample Rate: {dev_info['defaultSampleRate']}")
                    print(f"Input Latency - Default: {dev_info['defaultLowInputLatency']:.4f}, High: {dev_info['defaultHighInputLatency']:.4f}")
                    print(f"Output Latency - Default: {dev_info['defaultLowOutputLatency']:.4f}, High: {dev_info['defaultHighOutputLatency']:.4f}")
                    
                    # Try to open stream to test capabilities
                    try:
                        # Try exclusive mode
                        stream = p.open(
                            format=pyaudio.paFloat32,
                            channels=2,
                            rate=int(dev_info['defaultSampleRate']),
                            input=True,
                            input_device_index=i,
                            frames_per_buffer=960,
                            stream_flags=pyaudio.PaWinWasapiFlags.EXCLUSIVE
                        )
                        print("WASAPI Mode: Exclusive")
                        stream.close()
                    except Exception as e1:
                        try:
                            # Try shared mode
                            stream = p.open(
                                format=pyaudio.paFloat32,
                                channels=2,
                                rate=int(dev_info['defaultSampleRate']),
                                input=True,
                                input_device_index=i,
                                frames_per_buffer=960
                            )
                            print("WASAPI Mode: Shared")
                            stream.close()
                        except Exception as e2:
                            print(f"WASAPI Stream: Failed")
                            print(f"  Exclusive Mode Error: {str(e1)}")
                            print(f"  Shared Mode Error: {str(e2)}")
                        
            except Exception as e:
                print(f"Error getting device {i} info: {e}")
                
    except Exception as e:
        print(f"Error enumerating devices: {e}")
    finally:
        p.terminate()

if __name__ == '__main__':
    check_wasapi_devices()
