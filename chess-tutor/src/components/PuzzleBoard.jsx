import React, { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";

import { useChessStore } from "../stores/useChessStore";

export const chessboardRef = { current: null };

function PuzzleBoard({ onMove, puzzle, onHint }) {
  //const chessboardRef = { current: null };

  const [hintArrow, setHintArrow] = useState(null);
  const [boardOrientation, setBoardOrientation] = useState("white");

  const { chess, warningMessage } = useChessStore();

  useEffect(() => {
    if (puzzle) {
      // Determine the orientation based on whose turn it is in the puzzle's initial position
      const orientation = puzzle.fen.split(" ")[1] === "w" ? "white" : "black";
      setBoardOrientation(orientation);
    }
  }, [puzzle]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: chess.fen(),
      showNotation: true,
      orientation: boardOrientation,
      moveSpeed: "slow",
      onDrop: ({ source, target }) => {
        const moveSuccessful = onMove({ from: source, to: target });
        if (!moveSuccessful) return "snapback";
        chessboardRef.current.position(chess.fen());

        if (hintArrow) {
          chessboardRef.current.removeArrow(hintArrow);
          setHintArrow(null);
        }
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    return () => {
      if (chessboardRef.current) {
        chessboardRef.current.destroy();
      }
    };
  }, [chess, onMove, boardOrientation]);

  useEffect(() => {
    if (chessboardRef.current) {
      chessboardRef.current.position(chess.fen());
      chessboardRef.current.setOrientation(boardOrientation);
    }
  }, [chess.fen(), boardOrientation]);

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
