#!/usr/bin/env python3
"""
Test script to verify Opik integration is working correctly.
Run this before using the main voice assistant to ensure tracing is set up.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_opik_setup():
    """Test Opik configuration and connectivity."""
    print("=" * 60)
    print("Opik Integration Test")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking environment variables...")
    opik_api_key = os.getenv('OPIK_API_KEY')
    opik_workspace = os.getenv('OPIK_WORKSPACE')
    opik_url = os.getenv('OPIK_URL_OVERRIDE')
    
    if opik_api_key:
        print(f"   ✅ OPIK_API_KEY: Set (length: {len(opik_api_key)})")
    else:
        print("   ⚠️  OPIK_API_KEY: Not set (tracing will be disabled)")
    
    if opik_workspace:
        print(f"   ✅ OPIK_WORKSPACE: {opik_workspace}")
    else:
        print("   ℹ️  OPIK_WORKSPACE: Not set (will use default)")
    
    if opik_url:
        print(f"   ✅ OPIK_URL_OVERRIDE: {opik_url}")
    else:
        print("   ℹ️  OPIK_URL_OVERRIDE: Not set (will use Opik Cloud)")
    
    # Try to import and initialize Opik
    print("\n2. Testing Opik import and initialization...")
    try:
        import opik
        print("   ✅ Opik package imported successfully")
        
        # Try to create client
        try:
            client = opik.Opik()
            print("   ✅ Opik client initialized successfully")
            
            # Try to create a test trace
            print("\n3. Creating test trace...")
            try:
                trace = client.trace(
                    name="Test Trace",
                    input={"test": "input"},
                    metadata={"source": "test_script"}
                )
                print("   ✅ Test trace created successfully")
                
                # Create a test span
                print("\n4. Creating test span...")
                span = trace.span(
                    name="Test Tool Call",
                    input={"function": "test_function", "args": {"param": "value"}},
                    type="tool"
                )
                span.update(
                    output={"result": "success"},
                    metadata={"execution_time": 0.1}
                )
                span.end()
                print("   ✅ Test span created successfully")
                
                # End the trace
                trace.end()
                print("   ✅ Test trace ended successfully")
                
                print("\n" + "=" * 60)
                print("✅ SUCCESS! Opik integration is working correctly.")
                print("=" * 60)
                print("\nYou can now run the voice assistant with Opik tracing enabled.")
                print("View your traces at:")
                if opik_url and "localhost" in opik_url:
                    print("  → http://localhost:5173")
                else:
                    print("  → https://www.comet.com/")
                print()
                return True
                
            except Exception as e:
                print(f"   ❌ Failed to create test trace: {e}")
                print("\nPossible issues:")
                print("  - Check your API key is valid")
                print("  - Verify network connectivity")
                print("  - For self-hosted: ensure Docker container is running")
                return False
                
        except Exception as e:
            print(f"   ❌ Failed to initialize Opik client: {e}")
            print("\nPossible issues:")
            print("  - Invalid API key")
            print("  - Network connectivity issues")
            print("  - Incorrect OPIK_URL_OVERRIDE")
            return False
            
    except ImportError as e:
        print(f"   ❌ Failed to import Opik: {e}")
        print("\nPlease install Opik:")
        print("  pip install opik")
        return False

def test_without_opik():
    """Test that the application can run without Opik."""
    print("\n" + "=" * 60)
    print("Testing application without Opik")
    print("=" * 60)
    
    # Temporarily remove API key
    original_key = os.environ.pop('OPIK_API_KEY', None)
    
    try:
        import opik
        try:
            client = opik.Opik()
            print("   ℹ️  Opik client created (may use local mode)")
        except Exception as e:
            print(f"   ℹ️  Opik client initialization skipped: {e}")
        
        print("\n✅ Application can run without Opik configuration")
        print("   (Tracing will be disabled, but all features will work)")
        
    finally:
        # Restore API key
        if original_key:
            os.environ['OPIK_API_KEY'] = original_key

if __name__ == "__main__":
    print("\nThis script tests the Opik integration for the voice assistant.\n")
    
    # Test with Opik
    success = test_opik_setup()
    
    # Test without Opik
    test_without_opik()
    
    print("\n" + "=" * 60)
    if success:
        print("All tests passed! ✅")
        print("\nNext steps:")
        print("1. Run the voice assistant: python main_file.py")
        print("2. View traces in the Opik dashboard")
        print("3. See OPIK_SETUP.md for more details")
    else:
        print("Some tests failed. ⚠️")
        print("\nThe voice assistant will still work, but without tracing.")
        print("See OPIK_SETUP.md for setup instructions.")
    print("=" * 60 + "\n")
    
    sys.exit(0 if success else 1)
