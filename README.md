# Fundus Image Extract

## Overview
The Fundus Image Extract project provides a comprehensive system for managing fundus images with various features designed to enhance user experience and operational efficiency.

## Features
- **Standalone Image Uploads**: Users can upload fundus images independently.
- **Hospital/Lab Management**: Streamline management processes for hospitals and labs using this solution.
- **Disease Grading Schemes**: Implement various grading schemes for diseases based on the analysis of fundus images.
- **Role-Based Granular Access Control**: Control access to the system based on user roles, ensuring that sensitive data is protected.
- **Specific Task Roles**: Assign specific roles to users for targeted functionalities within the application.

## Setup Instructions
1. Clone the repository: `git clone https://github.com/drguptavivek/fundus_img_xtract.git`
2. Navigate into the directory: `cd fundus_img_xtract`
3. Install the required dependencies: `npm install`
4. Start the application: `npm start`
5. Follow the on-screen instructions to complete the setup.

## Workflow
The application allows users to upload images and runs OCR on Remedio images. All uploaded images undergo verification. During this process, an online image editor is used to hide patient data embedded directly in the images within the browser. Only verified images are coded in a confidential manner to ensure patient identity is protected.

## Python Virtual Environment Setup
1. Ensure Python is installed on your system. You can download it from [python.org](https://www.python.org/downloads/).
2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```
4. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## System Binary Installation
1. Install any necessary system binaries:
   ```bash
   sudo apt-get install package_name
   ```
2. Verify the installation:
   ```bash
   command --version
   ```
3. Configure the system binaries as required for the project.

Replace `package_name` with the actual package names needed for the specific setup.