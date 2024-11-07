import React, { useState } from "react";
import { useChessStore } from "../stores/useChessStore";
import { chessboardRef } from "./ChessBoard";

const ImportComponent = () => {
  const [fenInput, setFenInput] = useState("");
  const [pgnInput, setPgnInput] = useState("");
  const { chess, setFen, setPgn, updateMoveHistory } = useChessStore();

  const handleImport = () => {
    if (fenInput) {
      chess.load(fenInput);
      setFen(fenInput);
    } else if (pgnInput) {
      chess.loadPgn(pgnInput);
      setPgn(pgnInput);
    }
    chessboardRef.current.position(chess.fen());
    updateMoveHistory();
    setFenInput("");
    setPgnInput("");
  };

  return (
    <div className="mt-6">
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
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={!fenInput && !pgnInput}
        >
          Import
        </button>
      </div>
    </div>
  );
};

export default ImportComponent;
