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

  return (
    <div className="flex justify-between mt-2 p-2 bg-gray-100 rounded">
      <div>
        <span className="font-bold mr-2">White captured:</span>
        {capturedPieces.white.map(renderPiece)}
      </div>
      <div>
        <span className="font-bold mr-2">Black captured:</span>
        {capturedPieces.black.map(renderPiece)}
      </div>
    </div>
  );
}

export default CapturedPieces;
