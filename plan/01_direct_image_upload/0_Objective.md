# Plan: Direct Image Upload Feature

## 1. Objective

To implement a new feature allowing authorized users to directly upload one or more image files (e.g., `.jpg`, `.png`) without the need to associate them with any patient encounter. This provides a more flexible ingestion path than the current ZIP-only workflow.

## 2. Core User Stories

- As a contributor, I want to upload multiple images for a multiple patients all at once without having to create a ZIP file.
- As a contributor, I do not want to create  a new patient encounter for these images.
- As a data manager, I want to know images have been -  
    -   Which Hospital and Lab/unit of that hospital, 
    -   Disease - glaucoma, diabetic Retinopathy, AMD, corneal opacity, cataract, squint etc 
    -   Area - retina, cornea, lens, bilateral eyes, C-UV-AF, conjnctivafluorescein etc) 
    -   Captured from which type of camera (Topcon fundus camera, Remedio handheld, Bosch handheld, Volk Handheld, mobile phone, slit-lamp etc). 
    -   For retina  and lens images I want to know whether these were mydiatic or non-mydriatic images.
- As an Admin, I want to esnure security in image uploads and monitor the progress. I want to ensure uniqueness and I also want to set quota for users.


Some Clarifications

   1. Patient Information: The first user story mentions uploading images for "multiple patients," but the main objective is to not
      associate them with an encounter. Could you clarify this? Should the images be treated as completely anonymous, or should we
      capture a simple patient identifier for each image without creating a full patient record? - NO Patient Record

   2. New Metadata & Database: To store the new details (Hospital, Lab, Disease, Camera, etc.), I'll need to modify the database. Are
      you okay with me adding new tables and columns to support this? For instance, we might need new tables for Hospitals and Cameras,
      and a tagging system for diseases. --> YES as needed

   3. Image Uniqueness: For preventing duplicate uploads, do you agree that I should calculate a unique signature (an MD5 hash) for each
      image and block the upload if an identical image already exists anywhere in the system? --> YES


   4. User Quotas: Regarding the new quota requirement, could you specify:
       * Should the quota be based on the number of files or total storage size (MB/GB)? --> NUmber of Files
       * Should it apply to each user individually or to a user role? --> Individually to a user
       * What should happen when a user hits their quota? --> Disallow future uplaods still quota is revised

   5. "Contributor" Role: You mentioned a "contributor" role. Is this a new user role you'd like me to create in the system?--> yes

