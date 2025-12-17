#!/usr/bin/env python3
"""Fix smart quotes in Python files."""
import sys

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace smart quotes with regular quotes
    replacements = [
        ('\u201c', '"'),  # "
        ('\u201d', '"'),  # "
        ('\u2018', "'"),  # '
        ('\u2019', "'"),  # '
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Fixed: {filepath}")

if __name__ == "__main__":
    fix_file("modules/smart_engine.py")
    fix_file("modules/browser_flow_generator.py")
    fix_file("ve3_pro.py")
    print("Done!")
