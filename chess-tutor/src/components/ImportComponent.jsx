import React, { useState } from "react";
import useChessStore from "../stores/useChessStore";

const ImportComponent = () => {
  const [fenInput, setFenInput] = useState("");
  const [pgnInput, setPgnInput] = useState("");
  const { chess, setFen, setPgn } = useChessStore();

  const handleImport = () => {
    if (fenInput) {
      chess.load(fenInput);
      setFen(fenInput);
    } else if (pgnInput) {
      chess.load_pgn(pgnInput);
      setPgn(pgnInput);
    }
  };

  return (
    <div className="import-component">
      <div className="flex flex-col mb-4">
        <input
          type="text"
          value={fenInput}
          onChange={(e) => setFenInput(e.target.value)}
          placeholder="Enter FEN"
          className="mb-2 p-2 border rounded"
        />
        <input
          type="text"
          value={pgnInput}
          onChange={(e) => setPgnInput(e.target.value)}
          placeholder="Enter PGN"
          className="mb-2 p-2 border rounded"
        />
        <button
          onClick={handleImport}
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
        >
          Import
        </button>
      </div>
    </div>
  );
};

export default ImportComponent;
