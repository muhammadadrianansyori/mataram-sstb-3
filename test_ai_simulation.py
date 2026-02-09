import numpy as np
from modules.ai_validator import AIValidator, get_ai_status

def test_ai_simulation():
    print("Testing AI Validator in Simulation Mode...")
    
    # Check Status
    status = get_ai_status()
    print(f"Status: {status}")
    
    # Initialize Validator
    validator = AIValidator()
    
    # Create dummy image chips
    chip_start = np.zeros((224, 224, 6))
    chip_end = np.zeros((224, 224, 6))
    
    # Run Verification
    print("Running verify_change()...")
    result = validator.verify_change(chip_start, chip_end)
    
    # Check Result Format
    required_keys = ['verified', 'confidence', 'status', 'label', 'method']
    missing_keys = [k for k in required_keys if k not in result]
    
    if missing_keys:
        print(f"❌ FAIL: Missing keys in result: {missing_keys}")
    else:
        print("✅ PASS: Result format correct")
        print(f"Result: {result}")

if __name__ == "__main__":
    test_ai_simulation()
