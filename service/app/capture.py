"""Provisional VF-2 evidence. No anatomical landmark or pose model is claimed."""
from __future__ import annotations
import cv2
import numpy as np
from .decisions import build_decision
from .posture import (
    POSTURE_THRESHOLDS,
    analyze_posture,
    estimate_pose,
    landmarks_to_evidence,
)

CAPTURE_THRESHOLDS = dict(borderContrast=28, minimumSubjectArea=0.06,
                         minimumHeightFraction=0.65, maximumHeightFraction=0.94,
                         edgeMarginFraction=0.025, cordSearchTop=0.30,
                         cordSearchBottom=0.70, minimumCordWidthFraction=0.35,
                         maximumCordHeightFraction=0.06)


def capture_decision(view: str, image: np.ndarray, data: bytes) -> dict:
    record = build_decision(view, image, data)
    # Bound work and return coordinates in original-image units.
    original_h, original_w = image.shape[:2]
    ratio = min(1.0, 800 / max(original_h, original_w))
    small = cv2.resize(image, None, fx=ratio, fy=ratio) if ratio < 1 else image
    h, w = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    background = np.median(border, axis=0)
    distance = np.linalg.norm(lab - background, axis=2)
    mask = (distance > CAPTURE_THRESHOLDS['borderContrast']).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [c for c in contours if cv2.contourArea(c) / (h*w) > 0.06]
    evidence = []
    reasons = record['reasons'][:]
    framing = dict(status='unknown', method='border-background contrast candidate')
    cord = dict(status='unknown', method='horizontal colour/contrast band candidate')
    action = record['decision']
    if len(candidates) != 1 or float(np.std(border, axis=0).mean()) > 25:
        reasons.append('Use a plain contrasting background and show one person, head to feet; silhouette is ambiguous.')
        if action != 'recapture': action = 'review'
    else:
        contour = candidates[0]
        x, y, bw, bh = cv2.boundingRect(contour)
        box = dict(x=round(x/ratio), y=round(y/ratio), width=round(bw/ratio), height=round(bh/ratio))
        evidence.append(dict(kind='subject-candidate', label='Contrast silhouette candidate (not body landmarks)', box=box))
        height_fraction = bh/h
        clipped = x <= w*.025 or y <= h*.025 or x+bw >= w*.975 or y+bh >= h*.975
        framing.update(heightFraction=round(height_fraction, 4), edgeContact=clipped,
                       status='fail' if clipped or not .65 <= height_fraction <= .94 else 'pass')
        if framing['status'] == 'fail':
            action = 'recapture'
            reasons.append('Reframe: leave space above the head and below the feet; fill about 65–94% of image height.')
        roi = small[y:y+bh, x:x+bw]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Brightly coloured OR high local contrast thin horizontal bands.
        contrast = cv2.absdiff(gray, cv2.GaussianBlur(gray, (1, 21), 0))
        band_mask = (((hsv[:,:,1] > 100) & (hsv[:,:,2] > 60)) | (contrast > 40)).astype(np.uint8)*255
        top, bottom = int(bh*.30), int(bh*.70)
        band_mask[:top] = 0
        band_mask[bottom:] = 0
        band_mask = cv2.morphologyEx(band_mask, cv2.MORPH_OPEN, np.ones((1, max(3, int(bw*.15))), np.uint8))
        bands, _ = cv2.findContours(band_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [cv2.boundingRect(c) for c in bands]
        boxes = [b for b in boxes if b[2] >= bw*.35 and b[3] <= bh*.06 and b[2] / max(b[3],1) >= 4]
        if len(boxes) == 1:
            bx, by, cw, ch = boxes[0]
            cord.update(status='candidate', widthFraction=round(cw/bw, 4))
            evidence.append(dict(kind='cord-candidate', label='Possible cord — confirm natural-waist placement',
                                 box=dict(x=round((x+bx)/ratio), y=round((y+by)/ratio),
                                          width=round(cw/ratio), height=max(2, round(ch/ratio)))))
            reasons.append('Review the highlighted band: clothing trim can look like a cord. Confirm its natural-waist placement.')
            if action != 'recapture': action = 'review'
        else:
            cord['status'] = 'missing' if not boxes else 'ambiguous'
            action = 'recapture'
            reasons.append('Show one high-contrast thin cord around the natural waist; no unique cord candidate was found.')
    posture = dict(status='unknown', method='pose landmark model unavailable — human review required')
    landmarks = estimate_pose(small)
    if landmarks:
        analysis = analyze_posture(landmarks)
        posture = dict(
            status=('pass' if analysis['posture'] == 'pass' and analysis['headToFeet'] == 'pass'
                    else 'fail' if analysis['posture'] == 'fail' or analysis['headToFeet'] == 'fail'
                    else 'unknown'),
            method='MediaPipe Pose landmarks (33-point, provisional)',
            orientation=analysis['orientation'],
            headToFeet=analysis['headToFeet'],
            postureQuality=analysis['posture'],
            orientationMethod=analysis['orientationMethod'],
        )
        evidence.extend(landmarks_to_evidence(landmarks, original_w, original_h))
        if analysis['posture'] == 'fail' or analysis['headToFeet'] == 'fail':
            reasons.extend(analysis['reasons'])
            action = 'recapture'
        # A passing posture check still requires review; it never auto-approves.

    record.update(decision=action, reasons=reasons, evidence=evidence,
                  captureChecks=dict(framing=framing, waistCord=cord, posture=posture,
                    camera=dict(status='unknown', method='human review required')),
                  captureThresholds=CAPTURE_THRESHOLDS, evidenceVersion='vf2-posture-1',
                  postureThresholds=POSTURE_THRESHOLDS,
                  scope='Provisional exposure, blur, contrast-silhouette framing, cord and '
                        'pose-landmark posture candidates. Natural-waist placement, camera '
                        'level/distance and anatomical completeness require human review. '
                        'No measurement readiness or accuracy is asserted.')
    return record
