import React, { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";

import CapturedPieces from "./CapturedPieces";

import useChessStore from "../stores/useChessStore";
import useStockfishEvaluation from "../hooks/useStockfishEvaluation";

export const chessboardRef = { current: null };

function PuzzleBoard() {
  const bestMoveArrowRef = useRef(null);
  const [capturedPieces, setCapturedPieces] = useState({
    white: [],
    black: [],
  });

  const {
    chess,
    makeMove,
    warningMessage,
    evaluationData,
    isLoading,
    error,
    setEvaluationData,
    setIsLoading,
    setError,
  } = useChessStore();

  const {
    data,
    isLoading: evalIsLoading,
    error: evalError,
  } = useStockfishEvaluation(chess.fen());

  useEffect(() => {
    setEvaluationData(data);
    setIsLoading(evalIsLoading);
    setError(evalError);
  }, [
    data,
    evalIsLoading,
    evalError,
    setEvaluationData,
    setIsLoading,
    setError,
  ]);

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
        const moveSuccessful = makeMove(source, target);
        if (!moveSuccessful) return "snapback";
        chessboardRef.current.position(chess.fen());
        updateCapturedPieces();
        // Clear previous arrows
        chessboardRef.current.clearArrows();
        bestMoveArrowRef.current = null;
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);
    updateCapturedPieces();

    return () => {
      if (chessboardRef.current) {
        //chessboardRef.current.destroy();
      }
    };
  }, [chess, makeMove]);

  const getTurnText = () => {
    return chess.turn() === "w" ? "White to move" : "Black to move";
  };

  useEffect(() => {
    chessboardRef.current.position(chess.fen());
  }, [chess.fen()]);

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
    </>
  );
}

export default PuzzleBoard;
