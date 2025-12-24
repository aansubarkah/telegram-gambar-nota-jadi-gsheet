import asyncio
import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app_multi_users_qwen import TelegramGoogleSheetsBot
from credentials import CHUTES_API_KEY

async def test_text_parsing():
    """Test the text parsing functionality with the provided example"""
    
    # Example text from the user
    test_text = """selamat sore bapak/ibu mohon maaf untuk pengajuan tambhana buat fullback🙏 pak @Unknown number 
- Pertamina dex HDD 75L(3drigen):1.125k
- Pertamina dex exsa 50L(2drigen):750k
- Pertamax 50L (2 drigen ):637k
- busi untuk alcon (2pcs):50k
total :Rp.2.562.000"""
    
    print("Testing text parsing with the following input:")
    print("=" * 50)
    print(test_text)
    print("=" * 50)
    
    # Test the text parsing function
    result = await TelegramGoogleSheetsBot.convert_text_to_data(test_text)
    
    if result:
        print("\n✅ Text parsing successful!")
        print(f"Found {len(result)} items:")
        print("-" * 50)
        
        for i, item in enumerate(result, 1):
            print(f"Item {i}:")
            print(f"  Waktu: {item.get('waktu', 'N/A')}")
            print(f"  Penjual: {item.get('penjual', 'N/A')}")
            print(f"  Barang: {item.get('barang', 'N/A')}")
            print(f"  Harga: {item.get('harga', 0):,.2f}")
            print(f"  Jumlah: {item.get('jumlah', 0)}")
            print(f"  Service: {item.get('service', 0):,.2f}")
            print(f"  Pajak: {item.get('pajak', 0):,.2f}")
            print(f"  PPN: {item.get('ppn', 0):,.2f}")
            print(f"  Subtotal: {item.get('subtotal', 0):,.2f}")
            print()
        
        total = sum(item.get('subtotal', 0) for item in result)
        print(f"Total: {total:,.2f}")
        
    else:
        print("❌ Text parsing failed or no data found")
        return False
    
    return True

if __name__ == "__main__":
    # Check if API key is available
    if not CHUTES_API_KEY:
        print("❌ CHUTES_API_KEY not found in credentials.py")
        print("Please make sure the API key is properly configured.")
        sys.exit(1)
    
    # Run the test
    success = asyncio.run(test_text_parsing())
    
    if success:
        print("\n🎉 Test completed successfully!")
    else:
        print("\n💥 Test failed!")
        sys.exit(1)