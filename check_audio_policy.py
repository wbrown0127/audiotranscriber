import winreg

def check_render_device_settings(device_id):
    path = fr'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render\{device_id}'
    print(f"\nChecking device {device_id}...")
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            path,
            0,
            winreg.KEY_READ
        )
        
        try:
            # Check Properties subkey
            props_key = winreg.OpenKey(key, 'Properties')
            i = 0
            while True:
                try:
                    name, value, type_ = winreg.EnumValue(props_key, i)
                    print(f"Property: {name} = {value}")
                    i += 1
                except WindowsError:
                    break
            props_key.Close()
            
        except WindowsError as e:
            print(f"Error reading Properties: {e}")
            
        # Enumerate all values in main key
        i = 0
        while True:
            try:
                name, value, type_ = winreg.EnumValue(key, i)
                print(f"Setting: {name} = {value}")
                i += 1
            except WindowsError:
                break
                
        # List all subkeys
        i = 0
        while True:
            try:
                subkey = winreg.EnumKey(key, i)
                print(f"Found subkey: {subkey}")
                i += 1
            except WindowsError:
                break
                
    except WindowsError as e:
        print(f"Error accessing device: {e}")
    finally:
        try:
            key.Close()
        except:
            pass

if __name__ == '__main__':
    # Check first render device from previous output
    check_render_device_settings('02655149-aad7-4582-b01c-6161a3e85d7e')
