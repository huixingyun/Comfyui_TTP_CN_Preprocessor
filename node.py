import cv2
import numpy as np
from PIL import Image
import torch

def pil2tensor(image: Image) -> torch.Tensor:
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)

def tensor2pil(t_image: torch.Tensor) -> Image:
    return Image.fromarray(np.clip(255.0 * t_image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))

def apply_gaussian_blur(image_np, ksize=5, sigmaX=1.0):
    if ksize % 2 == 0:
        ksize += 1  # ksize must be odd
    blurred_image = cv2.GaussianBlur(image_np, (ksize, ksize), sigmaX=sigmaX)
    return blurred_image

def apply_guided_filter(image_np, radius, eps):
    # Convert image to float32 for the guided filter
    image_np_float = np.float32(image_np) / 255.0
    # Apply the guided filter
    filtered_image = cv2.ximgproc.guidedFilter(image_np_float, image_np_float, radius, eps)
    # Scale back to uint8
    filtered_image = np.clip(filtered_image * 255, 0, 255).astype(np.uint8)
    return filtered_image

def apply_low_pass_filter(image_np, cutoff_frequency, filter_strength):
    # Convert to float32 for FFT
    image_float = np.float32(image_np)
    
    # Process each channel separately
    result = np.zeros_like(image_float)
    
    for c in range(image_float.shape[2]):
        # Apply Fourier Transform
        f = np.fft.fft2(image_float[:, :, c])
        fshift = np.fft.fftshift(f)
        
        # Create a low pass filter mask
        rows, cols = image_float.shape[:2]
        crow, ccol = rows // 2, cols // 2
        
        # Create a mask with high values (1) at low frequencies
        # and low values (0) at high frequencies
        mask = np.zeros((rows, cols), np.float32)
        r = cutoff_frequency
        center = [crow, ccol]
        x, y = np.ogrid[:rows, :cols]
        mask_area = (x - center[0]) ** 2 + (y - center[1]) ** 2 <= r * r
        mask[mask_area] = 1
        
        # Apply smooth transition at the cutoff boundary based on filter_strength
        # The higher the filter_strength, the more abrupt the transition
        if filter_strength > 0:
            # Create distance matrix from center
            dist_from_center = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)
            # Create transition zone
            transition_zone = (dist_from_center > r) & (dist_from_center <= r + 50/filter_strength)
            # Apply exponential falloff in transition zone
            falloff = np.exp(-(dist_from_center[transition_zone] - r) * filter_strength / 10)
            mask[transition_zone] = falloff
        
        # Apply the mask
        fshift_filtered = fshift * mask
        
        # Inverse shift and inverse FFT
        f_ishift = np.fft.ifftshift(fshift_filtered)
        img_back = np.fft.ifft2(f_ishift)
        img_back = np.abs(img_back)
        
        # Normalize to original range
        result[:, :, c] = img_back
    
    # Convert back to uint8
    result = np.clip(result, 0, 255).astype(np.uint8)
    return result

class TTPlanet_Tile_Preprocessor_GF:
    def __init__(self, blur_strength=3.0, radius=7, eps=0.01):
        self.blur_strength = blur_strength
        self.radius = radius
        self.eps = eps

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "scale_factor": ("FLOAT", {"default": 1.00, "min": 1.00, "max": 8.00, "step": 0.05}),
                "blur_strength": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "radius": ("INT", {"default": 7, "min": 1, "max": 20, "step": 1}),
                "eps": ("FLOAT", {"default": 0.01, "min": 0.001, "max": 0.1, "step": 0.001}),
            },
            "optional": {}
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_output",)
    FUNCTION = 'process_image'
    CATEGORY = 'TTP_TILE'

    def process_image(self, image, scale_factor, blur_strength, radius, eps):
        ret_images = []
    
        for i in image:
            # Convert tensor to PIL for processing
            _canvas = tensor2pil(torch.unsqueeze(i, 0)).convert('RGB')
            img_np = np.array(_canvas)[:, :, ::-1]  # RGB to BGR
            
            # Apply Gaussian blur
            img_np = apply_gaussian_blur(img_np, ksize=int(blur_strength), sigmaX=blur_strength / 2)            

            # Apply Guided Filter
            img_np = apply_guided_filter(img_np, radius, eps)


            # Resize image
            height, width = img_np.shape[:2]
            new_width = int(width / scale_factor)
            new_height = int(height / scale_factor)
            resized_down = cv2.resize(img_np, (new_width, new_height), interpolation=cv2.INTER_AREA)
            resized_img = cv2.resize(resized_down, (width, height), interpolation=cv2.INTER_LINEAR)
            


            # Convert OpenCV back to PIL and then to tensor
            pil_img = Image.fromarray(resized_img[:, :, ::-1])  # BGR to RGB
            tensor_img = pil2tensor(pil_img)
            ret_images.append(tensor_img)
        
        return (torch.cat(ret_images, dim=0),)
        
class TTPlanet_Tile_Preprocessor_Simple:
    def __init__(self, blur_strength=3.0):
        self.blur_strength = blur_strength

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "scale_factor": ("FLOAT", {"default": 2.00, "min": 1.00, "max": 8.00, "step": 0.05}),
                "blur_strength": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 20.0, "step": 0.1}),
            },
            "optional": {}
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_output",)
    FUNCTION = 'process_image'
    CATEGORY = 'TTP_TILE'

    def process_image(self, image, scale_factor, blur_strength):
        ret_images = []
    
        for i in image:
            # Convert tensor to PIL for processing
            _canvas = tensor2pil(torch.unsqueeze(i, 0)).convert('RGB')
        
            # Convert PIL image to OpenCV format
            img_np = np.array(_canvas)[:, :, ::-1]  # RGB to BGR
        
            # Resize image first if you want blur to apply after resizing
            height, width = img_np.shape[:2]
            new_width = int(width / scale_factor)
            new_height = int(height / scale_factor)
            resized_down = cv2.resize(img_np, (new_width, new_height), interpolation=cv2.INTER_AREA)
            resized_img = cv2.resize(resized_down, (width, height), interpolation=cv2.INTER_LINEAR)
        
            # Apply Gaussian blur after resizing
            img_np = apply_gaussian_blur(resized_img, ksize=int(blur_strength), sigmaX=blur_strength / 2)
        
            # Convert OpenCV back to PIL and then to tensor
            _canvas = Image.fromarray(img_np[:, :, ::-1])  # BGR to RGB
            tensor_img = pil2tensor(_canvas)
            ret_images.append(tensor_img)
    
        return (torch.cat(ret_images, dim=0),)        

class TTPlanet_Tile_Preprocessor_cufoff:
    def __init__(self, blur_strength=3.0, cutoff_frequency=30, filter_strength=1.0):
        self.blur_strength = blur_strength
        self.cutoff_frequency = cutoff_frequency
        self.filter_strength = filter_strength

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "scale_factor": ("FLOAT", {"default": 1.00, "min": 1.00, "max": 8.00, "step": 0.05}),
                "blur_strength": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "cutoff_frequency": ("INT", {"default": 100, "min": 0, "max": 256, "step": 1}),
                "filter_strength": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1}),
            },
            "optional": {}
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_output",)
    FUNCTION = 'process_image'
    CATEGORY = 'TTP_TILE'

    def process_image(self, image, scale_factor, blur_strength, cutoff_frequency, filter_strength):
        ret_images = []
    
        for i in image:
            # Convert tensor to PIL for processing
            _canvas = tensor2pil(torch.unsqueeze(i, 0)).convert('RGB')
            img_np = np.array(_canvas)[:, :, ::-1]  # RGB to BGR

            # Apply low pass filter with new strength parameter
            img_np = apply_low_pass_filter(img_np, cutoff_frequency, filter_strength)

            # Resize image
            height, width = img_np.shape[:2]
            new_width = int(width / scale_factor)
            new_height = int(height / scale_factor)
            resized_down = cv2.resize(img_np, (new_width, new_height), interpolation=cv2.INTER_AREA)
            resized_img = cv2.resize(resized_down, (width, height), interpolation=cv2.INTER_LINEAR)
            
            # Apply Gaussian blur
            img_np = apply_gaussian_blur(img_np, ksize=int(blur_strength), sigmaX=blur_strength / 2)
            
            # Convert OpenCV back to PIL and then to tensor
            pil_img = Image.fromarray(resized_img[:, :, ::-1])  # BGR to RGB
            tensor_img = pil2tensor(pil_img)
            ret_images.append(tensor_img)
        
        return (torch.cat(ret_images, dim=0),)
        
        
def mask_to_pil(mask) -> Image:
    if isinstance(mask, torch.Tensor):
        mask_np = mask.squeeze().cpu().numpy()
    elif isinstance(mask, np.ndarray):
        mask_np = mask
    else:
        raise TypeError("Unsupported mask type")
    mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8))
    return mask_pil

class MaskBlackener:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("blackened_image",)
    FUNCTION = 'apply_black_mask'
    CATEGORY = 'Image Processing'

    def apply_black_mask(self, image, mask):
        # Convert image tensor to PIL
        image_pil = tensor2pil(image.squeeze(0)).convert('RGB')
        
        # Convert mask to PIL
        mask_pil = mask_to_pil(mask).convert('L')
        
        # Create a black image of the same size
        black_image = Image.new('RGB', image_pil.size, (0, 0, 0))
        
        # Apply the mask: use the original image where mask is black, and black image where mask is white
        blackened_image = Image.composite(black_image, image_pil, mask_pil)
        
        # Convert the result back to tensor
        blackened_image_tensor = pil2tensor(blackened_image)
        
        return (blackened_image_tensor,)

NODE_CLASS_MAPPINGS = {
    "TTPlanet_Tile_Preprocessor_GF": TTPlanet_Tile_Preprocessor_GF,
    "TTPlanet_Tile_Preprocessor_Simple": TTPlanet_Tile_Preprocessor_Simple,
    "TTPlanet_Tile_Preprocessor_cufoff": TTPlanet_Tile_Preprocessor_cufoff,
    "TTPlanet_inpainting_Preprecessor": MaskBlackener
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TTPlanet_Tile_Preprocessor_GF": "🪐TTP Tile Preprocessor HYDiT GF",
    "TTPlanet_Tile_Preprocessor_Simple": "🪐TTP Tile Preprocessor HYDiT  Simple",
    "TTPlanet_Tile_Preprocessor_cufoff": "🪐TTP Tile Preprocessor HYDiT cufoff",
    "TTPlanet_inpainting_Preprecessor" : "🪐TTP Inpainting Preprocessor HYDiT"
}