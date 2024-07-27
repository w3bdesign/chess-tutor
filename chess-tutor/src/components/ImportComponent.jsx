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
    chessboardRef.current.position(chess.fen());
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
<<<<<<< HEAD
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded disabled:opacity-50 disabled:cursor-not-allowed" 
=======
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
>>>>>>> b6a3767dc3cf54a91201106bfe3c9a941f0c6694
          disabled={!fenInput && !pgnInput}
        >
          Import
        </button>
      </div>
    </div>
  );
};

export default ImportComponent;
