import React, { useRef, useEffect, useState } from "react";

interface RichTextEditorProps {
  value: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
}

const RichTextEditor: React.FC<RichTextEditorProps> = ({
  value,
  onChange,
  placeholder = "",
  readOnly = false,
  className = "",
}) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const [content, setContent] = useState<string>(value);

  useEffect(() => {
    if (editorRef.current && value !== content) {
      // Preserve HTML content including images
      editorRef.current.innerHTML = value || "";
      setContent(value);
    }
  }, [value]);

  const handlePaste = async (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (readOnly) return;

    e.preventDefault();
    const clipboardData = e.clipboardData;

    // Check if clipboard contains image
    if (clipboardData.items) {
      for (let i = 0; i < clipboardData.items.length; i++) {
        const item = clipboardData.items[i];
        
        if (item.type.indexOf("image") !== -1) {
          const blob = item.getAsFile();
          if (blob) {
            const reader = new FileReader();
            reader.onload = (event) => {
              const imageDataUrl = event.target?.result as string;
              
              // Insert image into contentEditable div
              if (editorRef.current) {
                const selection = window.getSelection();
                const range = selection?.getRangeAt(0);
                
                if (range) {
                  // Create img element
                  const img = document.createElement("img");
                  img.src = imageDataUrl;
                  img.style.maxWidth = "100%";
                  img.style.height = "auto";
                  img.style.display = "block";
                  img.style.margin = "10px 0";
                  
                  // Insert image
                  range.deleteContents();
                  range.insertNode(img);
                  
                  // Move cursor after image
                  range.setStartAfter(img);
                  range.collapse(true);
                  selection?.removeAllRanges();
                  selection?.addRange(range);
                } else {
                  // Just append if no selection
                  const img = document.createElement("img");
                  img.src = imageDataUrl;
                  img.style.maxWidth = "100%";
                  img.style.height = "auto";
                  img.style.display = "block";
                  img.style.margin = "10px 0";
                  editorRef.current.appendChild(img);
                }
                
                // Update value with HTML content
                const newContent = editorRef.current.innerHTML;
                setContent(newContent);
                if (onChange) {
                  onChange(newContent);
                }
              }
            };
            reader.readAsDataURL(blob);
          }
          return;
        }
      }
    }

    // Fallback: paste as plain text if no image
    const text = clipboardData.getData("text/plain");
    if (text && editorRef.current) {
      const selection = window.getSelection();
      if (selection?.rangeCount) {
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(text);
        range.insertNode(textNode);
        range.setStartAfter(textNode);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      } else {
        editorRef.current.appendChild(document.createTextNode(text));
      }
      
      const newContent = editorRef.current.innerHTML;
      setContent(newContent);
      if (onChange) {
        onChange(newContent);
      }
    }
  };

  const handleInput = () => {
    if (editorRef.current && !readOnly) {
      const newContent = editorRef.current.innerHTML;
      setContent(newContent);
      if (onChange) {
        onChange(newContent);
      }
    }
  };

  return (
    <div
      ref={editorRef}
      contentEditable={!readOnly}
      onPaste={handlePaste}
      onInput={handleInput}
      className={`rich-text-editor ${className} ${readOnly ? "read-only" : ""}`}
      style={{
        minHeight: "120px",
        padding: "8px",
        border: "1px solid #dee2e6",
        borderRadius: "8px",
        outline: "none",
        backgroundColor: readOnly ? "#f8f9fa" : "#ffffff",
        cursor: readOnly ? "default" : "text",
        overflowWrap: "break-word",
        wordWrap: "break-word",
      }}
      data-placeholder={placeholder}
      suppressContentEditableWarning={true}
    />
  );
};

export default RichTextEditor;

