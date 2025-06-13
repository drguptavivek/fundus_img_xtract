import os
import shutil
import subprocess

# Define paths
processed_dir = './files/processed'
uploaded_dir = './files/uploaded'
db_path = './zip_processing.db'
models_script = 'models.py'

def move_files(src_dir, dest_dir):
    if not os.path.isdir(src_dir):
        print(f"Source directory not found: {src_dir}")
        return

    os.makedirs(dest_dir, exist_ok=True)

    for filename in os.listdir(src_dir):
        src_path = os.path.join(src_dir, filename)
        dest_path = os.path.join(dest_dir, filename)

        if os.path.isfile(src_path):
            shutil.move(src_path, dest_path)
            print(f"Moved: {src_path} -> {dest_path}")

def delete_file(file_path):
    if os.path.isfile(file_path):
        os.remove(file_path)
        print(f"Deleted file: {file_path}")
    else:
        print(f"File not found: {file_path}")

def run_models_script(script_path):
    if os.path.isfile(script_path):
        print(f"Executing {script_path}...")
        subprocess.run(['python', script_path], check=True)
    else:
        print(f"Script not found: {script_path}")

if __name__ == '__main__':
    move_files(processed_dir, uploaded_dir)
    delete_file(db_path)
    run_models_script(models_script)
