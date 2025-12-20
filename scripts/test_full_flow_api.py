#!/usr/bin/env python3
"""
VE3 Tool - TEST FULL FLOW API
=============================
Test đầy đủ flow: Bearer Token + reCAPTCHA → API aisandbox

Flow:
1. Lấy Bearer Token (từ browser hoặc input)
2. Giải reCAPTCHA Enterprise (qua 2Captcha)
3. Gọi API aisandbox để tạo ảnh
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.captcha_solver import CaptchaSolver, CaptchaService, CaptchaResult


class FlowAPITest:
    """Test Google Flow API với Bearer Token + reCAPTCHA."""

    BASE_URL = "https://aisandbox-pa.googleapis.com"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    # reCAPTCHA Enterprise Site Key
    RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

    def __init__(
        self,
        bearer_token: str,
        captcha_api_key: str = None,
        captcha_service: str = "2captcha"
    ):
        """
        Khởi tạo test.

        Args:
            bearer_token: Bearer token (ya29.xxx)
            captcha_api_key: API key của dịch vụ CAPTCHA
            captcha_service: "2captcha", "anticaptcha", "capsolver"
        """
        self.bearer_token = bearer_token.strip()
        self.captcha_api_key = captcha_api_key
        self.captcha_service = captcha_service
        self.recaptcha_token = None

        # Validate token
        if not self.bearer_token.startswith("ya29."):
            print("⚠️  Warning: Token should start with 'ya29.'")

        # Setup session
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Tạo HTTP session."""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Origin": "https://labs.google",
            "Referer": self.FLOW_URL,
            "X-Goog-Api-Key": "AIzaSyDjzfwD-jzXbS2QAMVbJDsHZvqN_Rm2N3o",
        })
        return session

    def solve_recaptcha(self, action: str = "pageview") -> bool:
        """
        Giải reCAPTCHA Enterprise.

        Returns:
            True nếu thành công
        """
        if not self.captcha_api_key:
            print("⚠️  No CAPTCHA API key provided, skipping...")
            return False

        print(f"\n🔐 Giải reCAPTCHA Enterprise...")
        print(f"   Site Key: {self.RECAPTCHA_SITE_KEY}")
        print(f"   Action: {action}")

        service_enum = {
            "2captcha": CaptchaService.TWOCAPTCHA,
            "anticaptcha": CaptchaService.ANTICAPTCHA,
            "capsolver": CaptchaService.CAPSOLVER
        }.get(self.captcha_service, CaptchaService.TWOCAPTCHA)

        solver = CaptchaSolver(self.captcha_api_key, service_enum)

        # Check balance first
        balance = solver.get_balance()
        print(f"   💰 Balance: ${balance:.4f}")

        if balance <= 0:
            print("   ❌ No balance!")
            return False

        # Solve
        result = solver.solve_flow_recaptcha(action=action)

        if result.success:
            self.recaptcha_token = result.token
            print(f"   ✅ Got reCAPTCHA token!")
            return True
        else:
            print(f"   ❌ Failed: {result.error}")
            return False

    def test_api_without_recaptcha(self) -> dict:
        """
        Test API mà KHÔNG có reCAPTCHA token.
        Xem server có yêu cầu không.
        """
        print(f"\n📡 Test API WITHOUT reCAPTCHA...")

        # Test 1: Project creation
        url = f"{self.BASE_URL}/v1internal/experiments"
        payload = {
            "toolName": "PINHOLE",
            "experimentType": "EXPERIMENT_TYPE_IMAGE_GEN_WORKSPACE"
        }

        try:
            response = self.session.post(url, json=payload, timeout=30)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")

            return {
                "status": response.status_code,
                "success": response.status_code == 200,
                "data": response.json() if response.status_code == 200 else None,
                "error": response.text if response.status_code != 200 else None
            }
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"status": 0, "success": False, "error": str(e)}

    def test_api_with_recaptcha(self) -> dict:
        """
        Test API VỚI reCAPTCHA token.
        """
        if not self.recaptcha_token:
            print("❌ No reCAPTCHA token! Call solve_recaptcha() first.")
            return {"success": False, "error": "No reCAPTCHA token"}

        print(f"\n📡 Test API WITH reCAPTCHA token...")

        # Add reCAPTCHA token to headers
        headers = {
            "X-Recaptcha-Token": self.recaptcha_token,
            "X-Recaptcha-Enterprise-Token": self.recaptcha_token,
        }

        url = f"{self.BASE_URL}/v1internal/experiments"
        payload = {
            "toolName": "PINHOLE",
            "experimentType": "EXPERIMENT_TYPE_IMAGE_GEN_WORKSPACE"
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")

            if response.status_code == 200:
                data = response.json()
                experiment_id = data.get("name", "").split("/")[-1]
                print(f"   ✅ Project created: {experiment_id}")
                return {
                    "status": 200,
                    "success": True,
                    "project_id": experiment_id,
                    "data": data
                }

            return {
                "status": response.status_code,
                "success": False,
                "error": response.text
            }

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"success": False, "error": str(e)}

    def test_image_generation(self, prompt: str = "A cute cat") -> dict:
        """
        Test tạo ảnh.
        """
        print(f"\n🎨 Test Image Generation...")
        print(f"   Prompt: {prompt}")

        # First create project
        result = self.test_api_with_recaptcha() if self.recaptcha_token else self.test_api_without_recaptcha()

        if not result.get("success"):
            return result

        project_id = result.get("project_id")
        if not project_id:
            # Try to extract from data
            data = result.get("data", {})
            name = data.get("name", "")
            project_id = name.split("/")[-1] if name else None

        if not project_id:
            return {"success": False, "error": "Could not get project ID"}

        print(f"   📁 Project ID: {project_id}")

        # Generate image
        url = f"{self.BASE_URL}/v1internal/imagegen:generate"
        payload = {
            "imageGenerationConfig": {
                "prompt": prompt,
                "guidanceScale": 100,
                "outputMimeType": "image/png",
                "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "numberOfImages": 1,
                "imageGenModelName": "GEM_PIX_2"
            },
            "toolName": "PINHOLE"
        }

        headers = {}
        if self.recaptcha_token:
            headers["X-Recaptcha-Token"] = self.recaptcha_token

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=120
            )
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                images = data.get("images", [])
                print(f"   ✅ Generated {len(images)} images!")
                return {
                    "success": True,
                    "images": images,
                    "data": data
                }
            else:
                print(f"   Response: {response.text[:500]}")
                return {
                    "success": False,
                    "status": response.status_code,
                    "error": response.text
                }

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"success": False, "error": str(e)}

    def test_endpoints(self):
        """Test các endpoint khác nhau."""
        endpoints = [
            ("/v1internal/experiments", "POST", {"toolName": "PINHOLE"}),
            ("/v1internal/imagegen:models", "GET", None),
            ("/v1internal/imagegen:quota", "GET", None),
        ]

        print(f"\n📋 Testing various endpoints...")

        results = []
        for endpoint, method, payload in endpoints:
            url = f"{self.BASE_URL}{endpoint}"
            print(f"\n   🔹 {method} {endpoint}")

            try:
                if method == "GET":
                    response = self.session.get(url, timeout=30)
                else:
                    response = self.session.post(url, json=payload, timeout=30)

                print(f"      Status: {response.status_code}")
                print(f"      Response: {response.text[:200]}...")

                results.append({
                    "endpoint": endpoint,
                    "status": response.status_code,
                    "success": response.status_code == 200
                })

            except Exception as e:
                print(f"      ❌ Error: {e}")
                results.append({
                    "endpoint": endpoint,
                    "status": 0,
                    "success": False,
                    "error": str(e)
                })

        return results


def main():
    """Main test function."""
    print("=" * 70)
    print("🚀 VE3 TOOL - FULL FLOW API TEST")
    print("=" * 70)
    print("Flow: Bearer Token + reCAPTCHA Enterprise → API aisandbox")
    print("=" * 70)

    # Get inputs
    print("\n📝 NHẬP THÔNG TIN:")

    bearer_token = input("Bearer Token (ya29.xxx): ").strip()
    if not bearer_token:
        print("❌ Bearer token is required!")
        return

    captcha_api_key = input("2Captcha API Key (Enter để bỏ qua): ").strip()
    captcha_service = "2captcha"

    if captcha_api_key:
        service_input = input("CAPTCHA Service (2captcha/anticaptcha/capsolver) [2captcha]: ").strip()
        if service_input:
            captcha_service = service_input

    # Create tester
    tester = FlowAPITest(
        bearer_token=bearer_token,
        captcha_api_key=captcha_api_key,
        captcha_service=captcha_service
    )

    # Step 1: Test without reCAPTCHA
    print("\n" + "=" * 70)
    print("STEP 1: Test API WITHOUT reCAPTCHA")
    print("=" * 70)
    result1 = tester.test_api_without_recaptcha()

    if result1.get("success"):
        print("\n✅ API works WITHOUT reCAPTCHA!")
        print("   → reCAPTCHA may not be required for this endpoint.")
    else:
        print("\n⚠️  API failed without reCAPTCHA.")
        print("   → May need reCAPTCHA token.")

    # Step 2: Test endpoints
    print("\n" + "=" * 70)
    print("STEP 2: Test Various Endpoints")
    print("=" * 70)
    endpoint_results = tester.test_endpoints()

    # Step 3: Test with reCAPTCHA (if API key provided)
    if captcha_api_key:
        print("\n" + "=" * 70)
        print("STEP 3: Solve reCAPTCHA Enterprise")
        print("=" * 70)

        if tester.solve_recaptcha(action="pageview"):
            print("\n" + "=" * 70)
            print("STEP 4: Test API WITH reCAPTCHA")
            print("=" * 70)
            result2 = tester.test_api_with_recaptcha()

            if result2.get("success"):
                print("\n✅ API works WITH reCAPTCHA!")

                # Step 5: Try image generation
                print("\n" + "=" * 70)
                print("STEP 5: Test Image Generation")
                print("=" * 70)

                prompt = input("Prompt (Enter for default 'A cute cat'): ").strip() or "A cute cat"
                gen_result = tester.test_image_generation(prompt)

                if gen_result.get("success"):
                    print("\n🎉 IMAGE GENERATION SUCCESS!")
                else:
                    print(f"\n❌ Generation failed: {gen_result.get('error')}")

    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Bearer Token: {bearer_token[:20]}...{bearer_token[-10:]}")
    print(f"reCAPTCHA Token: {'✅ Got' if tester.recaptcha_token else '❌ None'}")
    print(f"\nEndpoint Results:")
    for r in endpoint_results:
        status = "✅" if r.get("success") else "❌"
        print(f"   {status} {r['endpoint']}: {r['status']}")


if __name__ == "__main__":
    main()
