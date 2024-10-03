import os
import re

# Define the folder path
folder_path = r"C:\Users\hatem\OneDrive\Desktop\FazkerBot\المصحف"

# Set the starting point for renaming
start_number = 588

# Loop through all files in the folder
for filename in os.listdir(folder_path):
    # Construct the full file path
    full_path = os.path.join(folder_path, filename)

    # Check if the file is a thumbnail
    if filename.endswith("_thumb.jpg"):
        try:
            # Delete the thumbnail file
            os.remove(full_path)
            print(f"Deleted: {full_path}")
        except Exception as e:
            print(f"Error deleting {full_path}: {e}")

    # Check if the file is an actual photo
    elif filename.endswith(".jpg"):
        # Remove duplicate .jpg extension if it exists
        if filename.count(".jpg") > 1:
            new_filename = re.sub(r"(\.jpg)+$", ".jpg", filename)
            new_photo_path = os.path.join(folder_path, new_filename)

            try:
                os.rename(full_path, new_photo_path)
                print(f"Renamed: {full_path} to {new_photo_path}")
            except Exception as e:
                print(f"Error renaming {full_path}: {e}")

            # Update the full path to the new name for further processing
            full_path = new_photo_path
            filename = new_filename

        # Rename the actual photo based on its prefix
        if "photo_" in filename:
            # Extract the current number from the filename
            match = re.search(r'photo_(\d+)', filename)
            if match:
                current_number = int(match.group(1))
                # Check if the current number is less than or equal to the start number
                if current_number <= start_number:
                    # Decrement the number
                    new_number = current_number - 1
                    new_filename = f"photo_{new_number}.jpg"
                    new_photo_path = os.path.join(folder_path, new_filename)

                    try:
                        os.rename(full_path, new_photo_path)
                        print(f"Renamed: {full_path} to {new_photo_path}")
                    except Exception as e:
                        print(f"Error renaming {full_path}: {e}")

print("Operation completed.")
