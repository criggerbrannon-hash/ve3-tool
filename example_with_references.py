#!/usr/bin/env python3
"""
Example: Generate images với Reference Images
==============================================
Workflow đúng:
1. Upload ảnh reference trước → lấy 'name' (media_name)
2. Dùng 'name' đó trong imageInputs khi generate

KHÔNG gửi base64 trực tiếp vào imageInputs!
"""

from pathlib import Path
from modules.google_flow_api import (
    GoogleFlowAPI,
    AspectRatio,
    ImageInput,
    ImageInputType
)


def example_with_upload():
    """
    Example: Upload ảnh local làm reference, sau đó generate.
    """
    # 1. Khởi tạo API client
    token = "ya29.xxx..."  # Thay bằng token thật
    api = GoogleFlowAPI(bearer_token=token, verbose=True)

    # 2. Upload ảnh reference để lấy 'name'
    print("=" * 50)
    print("STEP 1: Upload reference images")
    print("=" * 50)

    ref_paths = [
        Path("./nv/nv1.png"),
        Path("./nv/nv2.png"),
        Path("./loc/loc2.png"),
    ]

    uploaded_refs = []
    for ref_path in ref_paths:
        if not ref_path.exists():
            print(f"  ⚠️ File not found: {ref_path}")
            continue

        success, img_input, error = api.upload_image(ref_path)

        if success and img_input:
            print(f"  ✅ Uploaded: {ref_path.name} -> name={img_input.name[:50]}...")
            uploaded_refs.append(img_input)
        else:
            print(f"  ❌ Failed: {ref_path.name} - {error}")

    if not uploaded_refs:
        print("❌ Không upload được reference nào!")
        return

    # 3. Generate ảnh với references
    print("\n" + "=" * 50)
    print("STEP 2: Generate với references")
    print("=" * 50)

    prompt = "A beautiful princess standing in an enchanted forest, magical atmosphere"

    success, images, error = api.generate_images(
        prompt=prompt,
        count=1,
        aspect_ratio=AspectRatio.LANDSCAPE,
        image_inputs=uploaded_refs  # Dùng ImageInput objects đã upload
    )

    if success and images:
        print(f"  ✅ Generated {len(images)} images!")

        # Download
        for i, img in enumerate(images):
            path = api.download_image(img, Path("./output"), f"result_{i}")
            if path:
                print(f"  📁 Saved: {path}")
    else:
        print(f"  ❌ Generate failed: {error}")


def example_with_generated_refs():
    """
    Example: Generate ảnh nhân vật trước, dùng làm reference cho scene.
    """
    token = "ya29.xxx..."  # Thay bằng token thật
    api = GoogleFlowAPI(bearer_token=token, verbose=True)

    # Step 1: Generate character
    print("=" * 50)
    print("STEP 1: Generate character")
    print("=" * 50)

    success, char_images, error = api.generate_images(
        prompt="A young princess with golden hair, wearing a blue dress, portrait style",
        count=1,
        aspect_ratio=AspectRatio.PORTRAIT
    )

    if not success or not char_images:
        print(f"❌ Character generation failed: {error}")
        return

    char_img = char_images[0]
    print(f"  ✅ Character generated!")
    print(f"  📌 media_name: {char_img.media_name}")  # QUAN TRỌNG: Lưu lại name này!

    # Save character
    api.download_image(char_img, Path("./nv"), "nv1")

    # Step 2: Generate scene với character reference
    print("\n" + "=" * 50)
    print("STEP 2: Generate scene với character reference")
    print("=" * 50)

    if not char_img.media_name:
        print("❌ Không có media_name từ character!")
        return

    # Dùng as_reference() để tạo ImageInput
    char_ref = char_img.as_reference(ImageInputType.REFERENCE)

    success, scene_images, error = api.generate_images(
        prompt="The princess walking through a magical forest with glowing flowers",
        count=1,
        aspect_ratio=AspectRatio.LANDSCAPE,
        image_inputs=[char_ref]  # Truyền reference
    )

    if success and scene_images:
        print(f"  ✅ Scene generated with character reference!")
        api.download_image(scene_images[0], Path("./img"), "scene_001")
    else:
        print(f"  ❌ Scene generation failed: {error}")


def show_correct_payload():
    """
    Hiển thị payload đúng vs sai.
    """
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                    PAYLOAD FORMAT                                 ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  ❌ SAI - Gửi base64 trực tiếp:                                  ║
║  {                                                                ║
║    "imageInputs": [{                                              ║
║      "name": "iVBORw0KGgoAAAANSUhEUgAA...",  // BASE64 = SAI!    ║
║      "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"               ║
║    }]                                                             ║
║  }                                                                ║
║                                                                   ║
║  ✅ ĐÚNG - Gửi media_name từ upload/generate response:           ║
║  {                                                                ║
║    "imageInputs": [{                                              ║
║      "name": "CAMaJDZjNTAxNzhjLTNjNjgtNDU0NC...",  // MEDIA NAME ║
║      "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"               ║
║    }]                                                             ║
║  }                                                                ║
║                                                                   ║
║  📌 Cách lấy media_name:                                         ║
║  1. Upload ảnh qua flowMedia:uploadImage → response có 'name'    ║
║  2. Hoặc Generate ảnh → response.media[].name                    ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    show_correct_payload()

    print("\nChọn example:")
    print("1. Upload local images làm reference")
    print("2. Generate character trước, dùng làm reference cho scene")

    # Uncomment để chạy:
    # example_with_upload()
    # example_with_generated_refs()
