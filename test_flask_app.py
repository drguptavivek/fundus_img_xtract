from flask import Flask, send_from_directory
import os

app = Flask(__name__)

@app.route('/test')
def test():
    directory = r'E:\fundus_img_xtract\fundus_img_xtract\files\direct_uploads'
    path = r'2025_09_03_user1\WhatsApp_Image_2025-07-29_at_12.11.08_PM_2.jpeg'
    
    print(f'Sending from directory: {directory}')
    print(f'Path: {path}')
    
    try:
        result = send_from_directory(directory, path, as_attachment=False)
        print(f'Result: {result}')
        return "Success"
    except Exception as e:
        print(f'Error: {e}')
        return f"Error: {e}"

if __name__ == '__main__':
    app.run(debug=True)