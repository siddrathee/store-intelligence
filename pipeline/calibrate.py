import cv2
import numpy as np

camera_pts = []
layout_pts = []

def select_camera_pts(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        camera_pts.append((x, y))
        print(f"Camera Point Recorded: ({x}, {y})")

def select_layout_pts(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        layout_pts.append((x, y))
        print(f"Layout Point Recorded: ({x}, {y})")

def main():
    # File paths for Store 1

    video_path = "data/store_1/cam1_zone.mp4" 
    layout_path = "data/store_1/layout.jpg"

    # Extract the first frame from the video
    cap = cv2.VideoCapture(video_path)
    success, cam_frame = cap.read()
    cap.release()

    if not success:
        print("Error: Could not load the video file.")
        return

    layout_img = cv2.imread(layout_path)
    if layout_img is None:
        print("Error: Could not load the layout image.")
        return

    print("STEP 1: Click 4 reference points on the floor in the Camera View.")
    cv2.imshow("Camera View", cam_frame)
    cv2.setMouseCallback("Camera View", select_camera_pts)
    cv2.waitKey(0) # Press any key to move to the next step
    cv2.destroyAllWindows()

    print("STEP 2: Click the exact same 4 points on the Layout Map in the identical order.")
    cv2.imshow("Layout Map", layout_img)
    cv2.setMouseCallback("Layout Map", select_layout_pts)
    cv2.waitKey(0) # Press any key to finish
    cv2.destroyAllWindows()

    if len(camera_pts) >= 4 and len(layout_pts) >= 4:
        # Take the first 4 points collected
        src_pts = np.float32(camera_pts[:4])
        dst_pts = np.float32(layout_pts[:4])

        # Calculate the perspective transformation matrix
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        np.save('homography_matrix.npy', matrix)
        
        print("\nSUCCESS: Transformation Matrix generated and saved to 'homography_matrix.npy'")
    else:
        print("\nERROR: 4 points were not successfully selected on both images.")

if __name__ == "__main__":
    main()