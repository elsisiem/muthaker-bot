import os
import re

# Define the directory containing your images
directory = r"C:\Users\hatem\OneDrive\Documents\GitHub\muthaker-bot\المصحف"

# Get a list of all files in the directory
files = os.listdir(directory)

# Step 1: Rename files in the range from -1 to 98 to a temporary format to avoid conflicts
for filename in files:
    match = re.match(r'photo_(-?\d+)\.jpg', filename)  # Handles negative numbers
    if match:
        number = int(match.group(1))
        # Only rename files between -1 and 98 to temp format
        if -1 <= number <= 98:
            temp_filename = f"temp_photo_{number}.jpg"
            os.rename(os.path.join(directory, filename), os.path.join(directory, temp_filename))

# Step 2: Rename the temporary files back to their final desired names
temp_files = os.listdir(directory)

for temp_filename in temp_files:
    match = re.match(r'temp_photo_(-?\d+)\.jpg', temp_filename)
    if match:
        number = int(match.group(1))
        # For files between -1 and 98, add 1 to the number
        if -1 <= number <= 98:
            new_number = number + 1
            new_filename = f"photo_{new_number}.jpg"
            os.rename(os.path.join(directory, temp_filename), os.path.join(directory, new_filename))
            print(f'Renamed: {temp_filename} -> {new_filename}')

print("Renaming complete!")
