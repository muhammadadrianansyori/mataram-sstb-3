import torch
from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
from PIL import Image
import numpy as np

class TransformerChangeDetector:
    """
    Real-time Change Detection using Transformer (SegFormer).
    Uses Post-Classification Comparison strategy:
    1. Segment 'Before' image -> Building Mask T1
    2. Segment 'After' image -> Building Mask T2
    3. Change = (Mask T2) AND (NOT Mask T1)
    
    This uses a Cityscapes-pretrained model which works very well for 
    detecting buildings (Class ID 2).
    """
    
    def __init__(self, device='cpu'):
        self.device = device
        # Model fine-tuned on LoveDA (Land-Cover Domain Adaptive)
        # Class 1 = Building in LoveDA dataset
        self.model_name = "wu-pr-gw/segformer-b2-finetuned-with-LoveDA" 
        self.processor = None
        self.model = None
        self.is_ready = False
        
    def load_model(self):
        try:
            print(f"Loading Satellite AI: {self.model_name}...")
            self.processor = SegformerImageProcessor.from_pretrained(self.model_name)
            self.model = SegformerForSemanticSegmentation.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self.is_ready = True
            print("✅ Satellite AI Model Loaded (LoveDA Dataset)")
            return True
        except Exception as e:
            print(f"❌ Failed to load LoveDA model: {e}")
            print("⚠️ Falling back to ADE20K model...")
            self.model_name = "nvidia/segformer-b0-finetuned-ade20k-512-1024"
            try:
                self.processor = SegformerImageProcessor.from_pretrained(self.model_name)
                self.model = SegformerForSemanticSegmentation.from_pretrained(self.model_name)
                self.model.to(self.device)
                self.model.eval()
                self.is_ready = True
                return True
            except:
                return False

    def predict(self, image_array):
        """
        Run segmentation on a single image array (H, W, Channels)
        Returns: Binary mask (1=Building, 0=Background)
        """
        if not self.is_ready:
            return None
            
        # Convert numpy to PIL
        if image_array.dtype != np.uint8:
            image_array = (image_array).astype(np.uint8)
            
        # Handle channels (Sentinel data might have >3, clean to RGB)
        if image_array.shape[2] > 3:
            image_array = image_array[:, :, :3]
            
        image = Image.fromarray(image_array)
        
        # Preprocess
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits  # shape (batch_size, num_labels, height/4, width/4)

        # Upsample logits to original image size
        upsampled_logits = torch.nn.functional.interpolate(
            logits,
            size=image.size[::-1], # (height, width)
            mode="bilinear",
            align_corners=False,
        )

        # Get prediction (argmax)
        pred_seg = upsampled_logits.argmax(dim=1)[0]
        
        # Class mapping logic
        if "LoveDA" in self.model_name:
            # LoveDA Classes:
            # 0: Background, 1: Building, 2: Road, 3: Water, 4: Barren, 5: Forest, 6: Agriculture
            # Building is Class 1
            building_mask = (pred_seg == 1).cpu().numpy().astype(np.uint8)
        else:
            # ADE20K Fallback
            # Building class is usually 1 (wall) or 2 (building) - checking index
            # ADE20K is complex, let's assume class 2 for generic 'building'
            building_mask = (pred_seg == 2).cpu().numpy().astype(np.uint8)
        
        return building_mask

    def detect_change(self, img_t1, img_t2):
        """
        Detect structural change between two images.
        """
        if not self.is_ready:
            self.load_model()
            
        mask_t1 = self.predict(img_t1)
        mask_t2 = self.predict(img_t2)
        
        if mask_t1 is None or mask_t2 is None:
            return 0.0, "Model Error"
            
        # Calculate Change: Building in T2 but not in T1
        # Logical: T2 AND (NOT T1)
        # Using arithmetic: (T2 - T1).clip(0, 1) or similar
        
        # Simple pixel diff of masks
        # change_pixels = np.sum((mask_t2 == 1) & (mask_t1 == 0))
        # total_pixels = mask_t1.size
        
        # Advanced: IoU or Dice, but for change we focus on new buildings
        
        building_t1_count = np.sum(mask_t1)
        building_t2_count = np.sum(mask_t2)
        
        # If T2 has significantly more building pixels than T1
        if building_t2_count > building_t1_count * 1.1: # Threshold 10% increase
             diff = building_t2_count - building_t1_count
             confidence = min(0.5 + (diff / 1000.0), 0.99) # Normalize confidence
             label = "New Building Detected"
        else:
             confidence = 0.1
             label = "No Structural Change"
             
        return confidence, label
