# Evolution to Closed-Loop Request-to-Data Provenance

`Request` models experimental protocols while `Data` records the raw collection results, with their association currently inferred through shared sample and session context. We decided to establish the architectural direction to introduce an explicit foreign key link from `Data` to `Request`, enabling automated collection engines to complete requests upon acquisition and establishing full closed-loop traceability from user protocol instructions to raw data files.
