# Herkenningsmodellen

Twee modellen, allebei gedraaid door onnxruntime, dat hier al staat als onderdeel van de
spraakherkenning. Geen grafische kaart nodig. Waar ze vandaan komen en hoe groot ze horen te
zijn staat in `backend/vision.py`.

| bestand | wat | grootte | herkomst | licentie |
|---|---|---|---|---|
| `face.onnx` | YuNet, gezichten | 227 KB | [opencv/face_detection_yunet](https://huggingface.co/opencv/face_detection_yunet) | MIT, zie `face.LICENSE` |
| `person.onnx` | YOLOv10n, personen | 9 MB | [onnx-community/yolov10n](https://huggingface.co/onnx-community/yolov10n) | AGPL 3.0 |

`face.onnx` staat in de repository: MIT mag meegeleverd worden, en het volgen van de spreker
werkt daardoor ook zonder internet.

`person.onnx` staat er **niet** in. YOLOv10 is AGPL 3.0, en die licentie werkt door op wat je
ermee meelevert. De app haalt het model bij het eerste gebruik op de computer van de kerk op,
zoals ze FFmpeg nu al doet, en geeft het zelf niet door. Wil je die licentie helemaal niet in
de buurt hebben, dan werkt het volgen ook met alleen `face.onnx`: het verliest de spreker
zodra die zich afwendt, en dat merk je aan een lagere dekking.
