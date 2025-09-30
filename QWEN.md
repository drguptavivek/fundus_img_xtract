# Fundus Image Manager
##  Technical Details
- **Backend:** Python, Flask
- **Database:** SQLAlchemy 
- **Custom JS:** Flash-Toasts.js, photoswipe, edit_image.js, app.js, 
-  **CSS:**  Bootstrap 5.3 via SCSS. Overides in app.css
- **Reusable Partials:** -  _forms.html for CSRF, _viewer_card.html
- **Environment:**  .env and .env.example

##  Common Commands
### Development
- `uv run  app.py` - Run the application 
- `uv pip install` - Install dependencies with uv
- `npn run build:css` - Build Theme 


## CODING PROTOCOL ##
**Coding Instructions**
- First understand the request and ask clarifying questions
- Explain your approach step-by-step before writing any code.
- No unrelated edits - focus on just the task you're on
- Follow PEP 8 style guidelines
- Apply PEP 484 type annotations
- Proper memory management
- Always close db sessions
- Choose efficent query loading
- Use proper dependency injection
- Implement proper request validation
- Implement proper error handling and exceptions
- Use explicit error handling, no unwraps in production code
- Build Logic First, then build front-end template. 
- Use Secure Coding practices
- Ensure CSRF protection in all forms  @templates/_forms.html   
- Enusre SQL Injection security
- Add allowed roles for each route
- Use Flash toasts for user feedback
- Use availabe styles only 
- Keep code modular using blueprints
- Include docstrings 
- Organize templates in sub-folders
- Ensure no data is lost.
- No sweeping changes
- Commit small, frequent changes for readable diff.


## 1. Project Overview
This project is a comprehensive system for an eye hospital to manage retinal fundus images. 
- Ingestion of ZIPs containg images and PDF reports of DR and glaucoam screening from Remedio Camera
- Ingestion of images from other cameras
- Scoping source of images, type of camera, Type of image
generation of curated datasets for training, cuual grading by resiednt and ophthalmologist wioth arbiotration
Capturing  Artificial Intelligence (AI) models grades for core diseases Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). 

## 2. System Architecture & Workflows

The application is built using Flask and is organized into modular blueprints, each handling a distinct set of features.
- **`app.py`**:  
- **`models.py`**: 



