from flask import send_from_directory
import os

directory = r'E:\fundus_img_xtract\fundus_img_xtract\files\direct_uploads'
path = r'2025_09_03_user1\WhatsApp_Image_2025-07-29_at_12.11.08_PM_2.jpeg'

print(f'Sending from directory: {directory}')
print(f'Path: {path}')

try:
    result = send_from_directory(directory, path, as_attachment=False)
    print(f'Result: {result}')
except Exception as e:
    print(f'Error: {e}')