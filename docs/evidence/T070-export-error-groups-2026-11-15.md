# T070 bounded numeric export diagnostic

Exact source `615ef877924faef1e137ef66c1522b7782e64e54`; [run #71](https://github.com/TudouXiang/edgevision-training/actions/runs/43663291587). Schema 2 diagnostic-only result.

Local frozen aggregate: 1037 backend passed /14 native opt-in skipped, 157 frontend passed, build/typecheck/contract checks passed. CI #70 ordinary checks and Windows succeeded. #71 native diagnostic, Windows and ordinary checks all completed successfully.

All native stages including cleanup passed. All PT repeat and source/network integrity observations were true. The following table contains closed aggregate observations, not tensor values or a production acceptance result.

|Arm|Direction|Input|Group|Elements|Mismatch count|Max absolute error|Max tolerance ratio|
|---|---|---|---|---:|---:|---:|---:|
|A|original_ort|gradient|boxes|33600|64|0.040679931640625|1.9578482715471708|
|A|original_ort|gradient|scores|16800|0|0.00006595253944396973|0.5033947069218045|
|A|original_ort|pattern|boxes|33600|0|0.002960205078125|0.1554648209263204|
|A|original_ort|pattern|scores|16800|0|0.000003844499588012695|0.02573693627031811|
|A|original_ort|zeros|boxes|33600|1|0.01708984375|1.4498878650555431|
|A|original_ort|zeros|scores|16800|0|0.000005710870027542114|0.0548786506487496|
|B|original_ort|gradient|boxes|33600|3|0.0172119140625|1.373723903104616|
|B|original_ort|gradient|scores|16800|0|0.000024944543838500977|0.1903937504263671|
|B|original_ort|pattern|boxes|33600|0|0.0040283203125|0.14968732359292214|
|B|original_ort|pattern|scores|16800|0|0.0000021085143089294434|0.01938858448240327|
|B|original_ort|zeros|boxes|33600|0|0.00628662109375|0.3393354577789569|
|B|original_ort|zeros|scores|16800|0|0.000002164393663406372|0.020798758008430212|
|C|fused_ort|gradient|boxes|33600|1|0.015594482421875|1.0343368974215679|
|C|fused_ort|gradient|scores|16800|0|0.000029712915420532227|0.22680085967762564|
|C|fused_ort|pattern|boxes|33600|0|0.0040283203125|0.13454955840724644|
|C|fused_ort|pattern|scores|16800|0|0.000003904104232788086|0.02894310410991415|
|C|fused_ort|zeros|boxes|33600|5|0.029754638671875|2.653850011186286|
|C|fused_ort|zeros|scores|16800|0|0.000009156763553619385|0.08799105965012735|
|C|original_fused|gradient|boxes|33600|60|0.038909912109375|1.7904716040464657|
|C|original_fused|gradient|scores|16800|0|0.00006729364395141602|0.5136309300630071|
|C|original_fused|pattern|boxes|33600|0|0.00433349609375|0.1565030258537488|
|C|original_fused|pattern|scores|16800|0|0.000002086162567138672|0.016074367175997487|
|C|original_fused|zeros|boxes|33600|25|0.03424072265625|3.254535526879996|
|C|original_fused|zeros|scores|16800|0|0.000011023133993148804|0.10592689319611875|
|C|original_ort|gradient|boxes|33600|10|0.027313232421875|1.3497112209355515|
|C|original_ort|gradient|scores|16800|0|0.00003758072853088379|0.286841719579031|
|C|original_ort|pattern|boxes|33600|0|0.00347900390625|0.2106766264889389|
|C|original_ort|pattern|scores|16800|0|0.0000028908252716064453|0.021431169523887125|
|C|original_ort|zeros|boxes|33600|0|0.006683349609375|0.6015492206081509|
|C|original_ort|zeros|scores|16800|0|0.000001866370439529419|0.017934901484033625|

## Interpretation and limits

All score comparisons passed the unchanged tolerance. Failures were confined to box coordinates, with finite, small absolute differences. This is consistent with floating-point drift but does not establish the responsible operator or prove that a different production threshold is justified. Fused PT versus ORT still fails on some inputs, so fusion is not a verified repair. Runs #68 and #71 each train a fresh model; their count differences are not a controlled effect of diagnostic code changes.

PyTorch documents that operation order and backend implementations can produce different floating-point results even for equivalent calculations ([2.15 numerical accuracy](https://docs.pytorch.org/docs/2.15/notes/numerical_accuracy.html)). Its [2.15 MKLDNN documentation](https://docs.pytorch.org/docs/2.15/notes/mkldnn.html) describes the backend enable control and IEEE internal precision defaults. These references support a numerical-backend hypothesis, not a specific diagnosis.

No tolerance, production exporter, artifact capability or acceptance threshold changed. Real-data product export remains blocked. A bounded backend control may be useful before proposing any contract change; arbitrary switch sweeps and changing tolerances merely to pass this sample are not justified.
