import cv2

points = []

def click_event(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append([x, y])
        print(f"[{x}, {y}],")
        
        # Draw a red dot where you clicked
        cv2.circle(img, (x, y), 3, (0, 0, 255), -1)
        cv2.imshow("Map Zones", img)

# Load the store layout
img = cv2.imread("data/store_1/layout.jpg")

if img is None:
    print("❌ Error: Could not load layout image.")
else:
    print("🖱️ Click the corners of a brand zone to get its coordinates.")
    print("Press 'q' to quit when done.")
    cv2.imshow("Map Zones", img)
    cv2.setMouseCallback("Map Zones", click_event)
    
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()