import os
import re

# Define the directory containing your images
directory = r"C:\Users\hatem\OneDrive\Documents\GitHub\muthaker-bot\المصحف"

# Get a list of all files in the directory
files = os.listdir(directory)

# Step 1: Rename all files to a temporary format to avoid conflicts
for filename in files:
    match = re.match(r'photo_(-?\d+)\.jpg', filename)
    if match:
        temp_filename = f"temp_{filename}"
        os.rename(os.path.join(directory, filename), os.path.join(directory, temp_filename))

# Step 2: Rename them from the temporary format to the final format
temp_files = os.listdir(directory)

for temp_filename in temp_files:
    match = re.match(r'temp_photo_(-?\d+)\.jpg', temp_filename)
    if match:
        number = int(match.group(1))
        
        if -1 <= number <= 98:
            new_number = number + 1
        else:
            continue
        
        new_filename = f"photo_{new_number}.jpg"
        os.rename(os.path.join(directory, temp_filename), os.path.join(directory, new_filename))
        print(f'Renamed: {temp_filename} -> {new_filename}')

print("Renaming complete!")
