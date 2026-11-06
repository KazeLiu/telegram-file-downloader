using System;
using System.IO;
using System.Runtime.InteropServices;

// IFileOperation's recycle-only mode and a pre-delete veto prevent a permanent-delete fallback.
public static class WindowsRecycle
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr binding, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IShellItem item);

    public static string Move(string path)
    {
        if (!Path.IsPathRooted(path) || !File.Exists(path) ||
            (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Expected an existing, regular local file.");
        var operation = (IFileOperation)Activator.CreateInstance(Type.GetTypeFromCLSID(
            new Guid("3AD05575-8857-4850-9277-11B85BDB8E09")));
        IShellItem item = null;
        try
        {
            var iid = typeof(IShellItem).GUID;
            SHCreateItemFromParsingName(path, IntPtr.Zero, ref iid, out item);
            operation.SetOperationFlags(0x20000000 | 0x00080000 | 0x00100000 | 0x0400 | 0x0010 | 0x0004 | 0x4000);
            var sink = new RecycleSink();
            operation.DeleteItem(item, sink);
            operation.PerformOperations();
            bool aborted;
            operation.GetAnyOperationsAborted(out aborted);
            if (aborted || !sink.Recycled || File.Exists(path))
                throw new IOException("Windows did not confirm a move to the Recycle Bin.");
            return sink.Destination;
        }
        finally
        {
            if (item != null) Marshal.ReleaseComObject(item);
            Marshal.ReleaseComObject(operation);
        }
    }

    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellItem
    {
        void BindToHandler(IntPtr binding, ref Guid handler, ref Guid iid, out IntPtr value);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint kind, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem other, uint hint, out int order);
    }

    [ComImport, Guid("947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileOperation
    {
        void Advise(IFileOperationProgressSink sink, out uint cookie);
        void Unadvise(uint cookie);
        void SetOperationFlags(uint flags);
        void SetProgressMessage([MarshalAs(UnmanagedType.LPWStr)] string message);
        void SetProgressDialog(IntPtr dialog);
        void SetProperties(IntPtr properties);
        void SetOwnerWindow(IntPtr window);
        void ApplyPropertiesToItem(IShellItem item);
        void ApplyPropertiesToItems([MarshalAs(UnmanagedType.IUnknown)] object items);
        void RenameItem(IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void RenameItems([MarshalAs(UnmanagedType.IUnknown)] object items, [MarshalAs(UnmanagedType.LPWStr)] string name);
        void MoveItem(IShellItem item, IShellItem destination, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void MoveItems([MarshalAs(UnmanagedType.IUnknown)] object items, IShellItem destination);
        void CopyItem(IShellItem item, IShellItem destination, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void CopyItems([MarshalAs(UnmanagedType.IUnknown)] object items, IShellItem destination);
        void DeleteItem(IShellItem item, IFileOperationProgressSink sink);
        void DeleteItems([MarshalAs(UnmanagedType.IUnknown)] object items);
        void NewItem(IShellItem destination, uint attributes, [MarshalAs(UnmanagedType.LPWStr)] string name,
            [MarshalAs(UnmanagedType.LPWStr)] string template, IFileOperationProgressSink sink);
        void PerformOperations();
        void GetAnyOperationsAborted([MarshalAs(UnmanagedType.Bool)] out bool aborted);
    }

    [ComVisible(true), Guid("04B0F1A7-9490-44BC-8B5E-9D3B9FB21970"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileOperationProgressSink
    {
        [PreserveSig] int StartOperations();
        [PreserveSig] int FinishOperations(int result);
        [PreserveSig] int PreRenameItem(uint flags, IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostRenameItem(uint flags, IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem destination);
        [PreserveSig] int PreMoveItem(uint flags, IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostMoveItem(uint flags, IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem destination);
        [PreserveSig] int PreCopyItem(uint flags, IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostCopyItem(uint flags, IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem destination);
        [PreserveSig] int PreDeleteItem(uint flags, IShellItem item);
        [PreserveSig] int PostDeleteItem(uint flags, IShellItem item, int result, IShellItem destination);
        [PreserveSig] int PreNewItem(uint flags, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostNewItem(uint flags, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name,
            [MarshalAs(UnmanagedType.LPWStr)] string template, uint attributes, int result, IShellItem item);
        [PreserveSig] int UpdateProgress(uint total, uint completed);
        [PreserveSig] int ResetTimer();
        [PreserveSig] int PauseTimer();
        [PreserveSig] int ResumeTimer();
    }

    [ComVisible(true), ClassInterface(ClassInterfaceType.None)]
    public class RecycleSink : IFileOperationProgressSink
    {
        public bool Recycled;
        public string Destination;
        public int PreDeleteItem(uint flags, IShellItem item) { return (flags & 0x80) != 0 ? 0 : unchecked((int)0x80004004); }
        public int PostDeleteItem(uint flags, IShellItem item, int result, IShellItem destination)
        {
            if (result < 0) return result;
            if (destination == null) return unchecked((int)0x80004004);
            IntPtr name;
            destination.GetDisplayName(0x80058000, out name);
            try { Destination = Marshal.PtrToStringUni(name); }
            finally { Marshal.FreeCoTaskMem(name); }
            Recycled = !String.IsNullOrEmpty(Destination);
            return Recycled ? 0 : unchecked((int)0x80004004);
        }
        public int StartOperations() { return 0; }
        public int FinishOperations(int result) { return result; }
        public int PreRenameItem(uint flags, IShellItem item, string name) { return 0; }
        public int PostRenameItem(uint flags, IShellItem item, string name, int result, IShellItem destination) { return result; }
        public int PreMoveItem(uint flags, IShellItem item, IShellItem folder, string name) { return 0; }
        public int PostMoveItem(uint flags, IShellItem item, IShellItem folder, string name, int result, IShellItem destination) { return result; }
        public int PreCopyItem(uint flags, IShellItem item, IShellItem folder, string name) { return 0; }
        public int PostCopyItem(uint flags, IShellItem item, IShellItem folder, string name, int result, IShellItem destination) { return result; }
        public int PreNewItem(uint flags, IShellItem folder, string name) { return 0; }
        public int PostNewItem(uint flags, IShellItem folder, string name, string template, uint attributes, int result, IShellItem item) { return result; }
        public int UpdateProgress(uint total, uint completed) { return 0; }
        public int ResetTimer() { return 0; }
        public int PauseTimer() { return 0; }
        public int ResumeTimer() { return 0; }
    }
}
