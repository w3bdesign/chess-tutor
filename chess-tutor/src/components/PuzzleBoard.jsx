import React, { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";

import CapturedPieces from "./CapturedPieces";

import useChessStore from "../stores/useChessStore";

export const chessboardRef = { current: null };

function PuzzleBoard({ onMove, puzzle, onHint }) {
  const [capturedPieces, setCapturedPieces] = useState({
    white: [],
    black: [],
  });
  const [hintArrow, setHintArrow] = useState(null);

  const { chess, makeMove, warningMessage } = useChessStore();

  const updateCapturedPieces = () => {
    const captured = { white: [], black: [] };
    const initialPieces = {
      p: 8,
      n: 2,
      b: 2,
      r: 2,
      q: 1,
      P: 8,
      N: 2,
      B: 2,
      R: 2,
      Q: 1,
    };

    const currentPieces = chess
      .board()
      .flat()
      .filter(Boolean)
      .reduce((acc, { type, color }) => {
        const pieceKey =
          color === "w" ? type.toUpperCase() : type.toLowerCase();
        acc[pieceKey] = (acc[pieceKey] || 0) + 1;
        return acc;
      }, {});

    for (const [piece, count] of Object.entries(initialPieces)) {
      const diff = count - (currentPieces[piece] || 0);
      if (diff > 0) {
        const color = piece === piece.toUpperCase() ? "black" : "white";
        captured[color].push(...Array(diff).fill(piece));
      }
    }

    setCapturedPieces(captured);
  };
  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: chess.fen(),
      showNotation: true,
      onDrop: ({ source, target }) => {
        const moveSuccessful = onMove({ from: source, to: target });
        if (!moveSuccessful) return "snapback";
        chessboardRef.current.position(chess.fen());
        updateCapturedPieces();
        if (hintArrow) {
          chessboardRef.current.removeArrow(hintArrow);
          setHintArrow(null);
        }
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);
    updateCapturedPieces();

    return () => {
      if (chessboardRef.current) {
        //chessboardRef.current.destroy();
      }
    };
  }, [chess, onMove]);

  useEffect(() => {
    chessboardRef.current.position(chess.fen());
  }, [chess.fen()]);

  const getTurnText = () => {
    return chess.turn() === "w" ? "White to move" : "Black to move";
  };

  const handleHint = () => {
    if (puzzle && puzzle.solution.length > 0) {
      const hintMove = puzzle.solution[0];
      const from = hintMove.slice(0, 2);
      const to = hintMove.slice(2, 4);

      if (hintArrow) {
        chessboardRef.current.removeArrow(hintArrow);
      }

      const newHintArrow = chessboardRef.current.addArrow({
        color: "#007bff",
        start: from,
        end: to,
        size: "medium",
        opacity: "60%",
      });

      setHintArrow(newHintArrow);
      onHint();
    }
  };

  return (
    <>
      {warningMessage && (
        <p className="text-red-500 p-2 mb-2 font-semibold">{warningMessage}</p>
      )}
      <p className="text-lg p-4 mt-2 mb-4 font-semibold shadow border bg-white rounded w-full">
        {getTurnText()}
      </p>
      <div
        id="myBoard"
        className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
      ></div>
      <button
        onClick={handleHint}
        className="mt-4 bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded mr-6"
      >
        Hint
      </button>
    </>
  );
}

export default PuzzleBoard;