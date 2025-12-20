#!/usr/bin/env python3
"""
QUICK TEST - reCAPTCHA Enterprise cho Google Labs Flow
======================================================
Site Key: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV

Chạy: python scripts/quick_test_recaptcha.py <2CAPTCHA_API_KEY>
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.captcha_solver import CaptchaSolver, CaptchaService


def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("QUICK TEST - reCAPTCHA Enterprise")
        print("=" * 60)
        print("\nUsage: python scripts/quick_test_recaptcha.py <API_KEY> [service]")
        print("\nServices: 2captcha (default), anticaptcha, capsolver")
        print("\nExample:")
        print("  python scripts/quick_test_recaptcha.py YOUR_2CAPTCHA_KEY")
        print("  python scripts/quick_test_recaptcha.py YOUR_KEY capsolver")
        return

    api_key = sys.argv[1]
    service_name = sys.argv[2] if len(sys.argv) > 2 else "2captcha"

    print("=" * 60)
    print("QUICK TEST - reCAPTCHA Enterprise")
    print("=" * 60)
    print(f"\nService: {service_name}")
    print(f"Site Key: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV")
    print(f"Target: https://labs.google/fx/vi/tools/flow")

    # Map service name
    service_map = {
        "2captcha": CaptchaService.TWOCAPTCHA,
        "anticaptcha": CaptchaService.ANTICAPTCHA,
        "capsolver": CaptchaService.CAPSOLVER
    }
    service = service_map.get(service_name.lower(), CaptchaService.TWOCAPTCHA)

    # Create solver
    solver = CaptchaSolver(api_key, service)

    # Check balance
    print(f"\n[1] Checking balance...")
    balance = solver.get_balance()
    print(f"    Balance: ${balance:.4f}")

    if balance <= 0:
        print("\n    No balance! Please top up your account.")
        return

    # Solve reCAPTCHA
    print(f"\n[2] Solving reCAPTCHA Enterprise...")
    result = solver.solve_flow_recaptcha(action="pageview")

    if result.success:
        print(f"\n{'=' * 60}")
        print("SUCCESS!")
        print("=" * 60)
        print(f"\nToken (first 100 chars):")
        print(f"  {result.token[:100]}...")
        print(f"\nToken length: {len(result.token)} chars")
        print(f"Solve time: {result.solve_time:.1f}s")
        print(f"\nFull token saved to: recaptcha_token.txt")

        # Save token
        with open("recaptcha_token.txt", "w") as f:
            f.write(result.token)
    else:
        print(f"\nFAILED: {result.error}")


if __name__ == "__main__":
    main()
