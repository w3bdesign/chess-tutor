function CapturedPieces({ capturedPieces }) {
  const renderPiece = (piece, index) => (
    <span key={index} className="text-2xl mr-1">
      {piece === "p"
        ? "♙"
        : piece === "n"
        ? "♘"
        : piece === "b"
        ? "♗"
        : piece === "r"
        ? "♖"
        : piece === "q"
        ? "♕"
        : piece === "P"
        ? "♟"
        : piece === "N"
        ? "♞"
        : piece === "B"
        ? "♝"
        : piece === "R"
        ? "♜"
        : piece === "Q"
        ? "♛"
        : ""}
    </span>
  );

  const whiteCaptured = capturedPieces.white.length > 0;
  const blackCaptured = capturedPieces.black.length > 0;

  if (!whiteCaptured && !blackCaptured) {
    return null; // Don't render anything if no pieces are captured
  }

  return (
    <div className="flex justify-between mt-2 p-2 bg-gray-100 rounded">
      {whiteCaptured && (
        <div>
          <span className="font-bold mr-2">White captured:</span>
          {capturedPieces.white.map(renderPiece)}
        </div>
      )}
      {blackCaptured && (
        <div>
          <span className="font-bold mr-2">Black captured:</span>
          {capturedPieces.black.map(renderPiece)}
        </div>
      )}
    </div>
  );
}

export default CapturedPieces;
