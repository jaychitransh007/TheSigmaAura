	Virtual try-on: replace only the clothing on the person with the target garment.

	The person in the image must remain exactly the same. Preserve the original identity, pose, body shape, body proportions, and body silhouette.

	The body geometry is fixed and must not change.

	Preserve exactly:
	- waist width
	- torso width
	- torso length
	- hip width
	- shoulder width
	- arm thickness
	- leg thickness
	- leg length
	- overall body proportions

	The outer contour of the body must remain identical to the input image.

	Do not modify the body outline, including the waist, hips, torso, shoulders, arms, or legs.

	The garment must adapt to the existing body shape. The body must NOT change to fit the garment.

	Important rule: treat the person's body as immutable geometry.

	Only replace the clothing with the target garment while keeping the same body silhouette.

	Preserve:
	- original pose and posture
	- camera perspective
	- background structure
	- scene lighting

	The output must look like the same person wearing the new garment while maintaining the exact same body shape and silhouette as the original image. The garment must drape naturally over the body and must not pull inward at the waist or torso. Maintain the same waist-to-hip ratio and torso proportions as in the original image.